#!/usr/bin/perl
#======================================================================#
# Program => melate.pl (In Perl 5.0)                     version 1.0.0 #
#======================================================================#
# Autor         => Fernando "El Pop" Romo           (pop@cofradia.org) #
# Creation date => 22/April/2024                                       #
#----------------------------------------------------------------------#
# Info => This program gives statistical information of the numbers    #
#         of the mexican version of lotto.                             #
#----------------------------------------------------------------------#
#        This code are released under the GPL 3.0 License.             #
#                                                                      #
#                     (c) 2024 - Fernando Romo                         #
#                                                                      #
# This program is free software: you can redistribute it and/or modify #
# it under the terms of the GNU General Public License as published by #
# the Free Software Foundation, either version 3 of the License, or    #
# (at your option) any later version.                                  #
#                                                                      #
# This program is distributed in the hope that it will be useful, but  #
# WITHOUT ANY WARRANTY; without even the implied warranty of           #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU    #
# General Public License for more details.                             #
#                                                                      #
# You should have received a copy of the GNU General Public License    #
# along with this program. If not, see <https://www.gnu.org/licenses/> #
#======================================================================#
use strict;
use DBI;            # Interface to Database
use File::Copy;     # File cp or mv
use Text::Diff;     # Diff of text files
use Getopt::Long;   # Handle the arguments passed to the program
use LWP::UserAgent; # Web user agent class
use Pod::Usage;     # Perl documentation for help

# Terminal Colors
use constant {
    RESET     => "\033[0m",
    BRIGHT    => "\033[1m",
    DIM       => "\033[2m",
    UNDERLINE => "\033[3m",
    BLINK     => "\033[5m",
    REVERSE   => "\033[7m",
    HIDDEN    => "\033[8m",

    FG_BLACK    => "\033[30m",
    FG_RED      => "\033[31m",
    FG_GREEN    => "\033[32m",
    FG_YELLOW   => "\033[33m",
    FG_BLUE     => "\033[34m",
    FG_MAGENTA  => "\033[35m",
    FG_CYAN     => "\033[36m",
    FG_WHITE    => "\033[37m",

    FG_BRIGHT_BLACK    => "\033[90m",
    FG_BRIGHT_RED      => "\033[91m",
    FG_BRIGHT_GREEN    => "\033[92m",
    FG_BRIGHT_YELLOW   => "\033[93m",
    FG_BRIGHT_BLUE     => "\033[94m",
    FG_BRIGHT_MAGENTA  => "\033[95m",
    FG_BRIGHT_CYAN     => "\033[96m",
    FG_BRIGHT_WHITE    => "\033[97m",

    BG_BLACK    => "\033[40m",
    BG_RED      => "\033[41m",
    BG_GREEN    => "\033[42m",
    BG_YELLOW   => "\033[43m",
    BG_BLUE     => "\033[44m",
    BG_MAGENTA  => "\033[45m",
    BG_CYAN     => "\033[46m",
    BG_WHITE    => "\033[47m",

    BG_BRIGHT_BLACK    => "\033[100m",
    BG_BRIGHT_RED      => "\033[101m",
    BG_BRIGHT_GREEN    => "\033[102m",
    BG_BRIGHT_YELLOW   => "\033[103m",
    BG_BRIGHT_BLUE     => "\033[104m",
    BG_BRIGHT_MAGENTA  => "\033[105m",
    BG_BRIGHT_CYAN     => "\033[106m",
    BG_BRIGHT_WHITE    => "\033[107m",
};

# Customize color output
my %lottery_info_options = ('color' => BG_BRIGHT_YELLOW . BRIGHT .FG_BLACK,);

my %header_numbers_options = ('color' => BG_BRIGHT_WHITE . BRIGHT . FG_BLACK,);

my %matrix_options = ('color' => { 'draw'   => BG_WHITE . BRIGHT . FG_BLACK,
                                   'date'   => BG_WHITE . FG_BLACK,
                                   'detail' => BG_BLACK . BRIGHT . FG_WHITE, }, );

my %totals_options = ('leyend' => 'Totals',
                      'color' => { 'leyend' => BG_BRIGHT_WHITE . BRIGHT . FG_BLACK,
                                   'detail' => BG_RED   . BRIGHT . FG_WHITE, }, );

my %graph_options = ('color' => { 'axis'   => BG_BRIGHT_WHITE . BRIGHT . FG_BLACK,
                                  'bar'    => BG_BRIGHT_CYAN  . BRIGHT . FG_BLACK,
                                  'balls'  => BG_BRIGHT_WHITE . BRIGHT . FG_BLACK,
                                  'totals' => BG_RED   . BRIGHT . FG_WHITE,}, );

my %ocurrences_options = ('leyend' => 'Totals',
                          'color' => { 'header' => BG_RED . BRIGHT . FG_BLACK,
                                       'detail' => BG_RED . BRIGHT . FG_WHITE, }, );

my %weight_ocurrences_options = ('leyend' => 'Weight Totals',
                                 'color' => { 'header' => BG_GREEN . BRIGHT . FG_BLACK,
                                              'detail' => BG_GREEN . BRIGHT . FG_WHITE, }, );

my %break_ocurrences_options = ('leyend' => 'Break zone',
                                'color' => { 'header' => BG_CYAN . BRIGHT . FG_BLACK,
                                             'detail' => BG_CYAN . BRIGHT . FG_WHITE, }, );

my %break_options = ('leyend' => 'Subtotal ',
                      'color' => { 'leyend' => BG_WHITE . BRIGHT . FG_BLACK,
                                   'detail' => BG_CYAN . BRIGHT . FG_BLACK,, }, );

# Command Line options
my %options = ();
GetOptions(\%options,
           'count=i',
           'download',
           'summary',
           'graph',
           'break=i',
           'text',
           'weight',
           'morning',
           'night',
);

my $init_flag = 0;

my $work_dir = $ENV{'HOME'} . '/.melate'; # keys directory
# if not exists the work directory, creates and put the init_flag on
unless (-e "$work_dir/chispazo.db") {
    mkdir($work_dir);
    $init_flag = 1;
}

# Open or create SQLite DB
my $dbh = DBI->connect("dbi:SQLite:dbname=$work_dir/chispazo.db","","");
$dbh->{PrintError} = 0; # Disable automatic  Error Handling

# if not exists the db schema, creates and star a initial load of the results
if ($init_flag) {
    # init the db schema
    init_db();
}

# prepare in advanced the work query
my $SQL_Code = "select * from results order by draw desc limit ?;";
my $sth_results = $dbh->prepare($SQL_Code);

$SQL_Code = "select draw from results where draw = ?;";
my $sth_read = $dbh->prepare($SQL_Code);

$SQL_Code = "insert into results(draw, date_time, r1, r2, r3, r4, r5)
                            values( ?, ?, ?, ?, ?, ?, ?);";
my $sth_insert = $dbh->prepare($SQL_Code);

if ($init_flag) {
    # Load the results
    download_results();
    # clean up the DB
    $dbh->do('vacuum;');
}

#-------------------------------------------#
# Create the initial SQLite database schema #
#-------------------------------------------#
sub init_db {
    print "Init DB\n";
    # Create the results table of the lottery draw
    $SQL_Code = "
        CREATE TABLE results (
            id         INTEGER PRIMARY KEY,
            draw       integer NOT NULL,
            date_time  TEXT    NOT NULL,
            r1         integer,
            r2         integer,
            r3         integer,
            r4         integer,
            r5         integer
        );";
    $dbh->do($SQL_Code);
    # Create index on results table
    $SQL_Code = "CREATE INDEX in_draw_results on results(draw);";
    $dbh->do($SQL_Code);
    $SQL_Code = "CREATE INDEX in_dt_results on results(date_time);";
    $dbh->do($SQL_Code);
} # End sub init_db()

#--------------------------------------#
# Search if the record already exists  #
#--------------------------------------#
sub already_on_results {
    my $draw = shift;
    my $already = 0;
    my $ret = $sth_read->execute($draw);
    while (my $read_ref = $sth_read->fetchrow_hashref) {
        $already++;
    }
    $sth_read->finish();
    return $already
} # en sub _already_on_results()

#-----------------------------#
# Get the file from http host #
#-----------------------------#
sub get_file {
    my ($url,$target) = @_;
    my $status = 1;
    my $ua = LWP::UserAgent->new(
        agent => 'melate/1.0',
        keep_alive => 1,
        env_proxy  => 1,
        ssl_opts => { verify_hostname => 0,
                      SSL_verify_mode => 0x00,
                    },
    );
    $| = 1; # autoflush
    open(FILE, ">", $target) or $status = 0;
    if ($status) {
        my $res = $ua->request(
            HTTP::Request->new(GET => $url),
            sub {
                print FILE $_[0] or $status = 0 ;
            }
        );
        close(FILE) or $status = 0 ;
    }
    undef $ua;
    return $status;
} # sub get_file()

#-----------------------------------------------#
# Download the files from the lottery authority #
# and insert the new results into the SQLite DB #
#-----------------------------------------------#
sub download_results {
    print "Download results from Pronosticos Deportivos\n";

    # check if exists the work directory
    unless (-e "$work_dir/results/Chispazo.csv") {
        open(TOUCH, ">", "$work_dir/results/Chispazo.csv") or die;
        close(TOUCH);
    }

    # move working files
    move("$work_dir/results/Chispazo.csv", "$work_dir/results/Chispazo.old");
    # download with LWP::UserAgent, is faster than wget
    my $process_flag = 0;
    $process_flag = eval { get_file('https://pronosticos.gob.mx/Documentos/Historicos/Chispazo.csv',"$work_dir/results/Chispazo.csv") };
    if ($process_flag) {
        # obtain only the difference of record to process
        my $diff = diff( "$work_dir/results/Chispazo.old", "$work_dir/results/Chispazo.csv");
        my @changes = $diff =~ /\+(\d+,.*?)\n/g;
        # process each result and insert into the results table
        foreach my $new (sort { $a <=> $b } @changes) {
            
            my ($sorteo,$r1,$r2,$r3,$r4,$r5,$fecha) = split(/,/,$new);
            my ($day, $month, $year) = split(/\//,$fecha);
            my $date_time = sprintf("%04d-%02d-%02d",$year, $month, $day);
            unless( already_on_results($sorteo) ) {
                print "    $sorteo,$date_time, $r1,$r2,$r3,$r4,$r5\n" unless($init_flag);
                # insert the new record if not previously exists
                $sth_insert->execute($sorteo,$date_time,$r1,$r2,$r3,$r4,$r5);
            }
        }
        # remove old file
        unlink("$work_dir/results/Chispazo.old");
    }
    else {
        move("$work_dir/results/Chispazo.old", "$work_dir/results/Chispazo.csv");
        print "Error: Problem downloading file from https://pronosticos.gob.mx/Documentos/Historicos/Chispazo.csv\n";
    }
} # end sub download_results()

#---------------------#
# Shows balls numbers #
#---------------------#
sub header_numbers {
    my ($range, $options_ref) = @_;
        my $x_rep = (3 * $range) +5;
        print $options_ref->{color} unless($options{'text'});
        print '    #     Date     ';
        for (my $i = 1;$i<=$range;$i++) {
            print sprintf("%02d ",$i);
        }
        print ' ';
        print RESET unless($options{'text'});
        print "\n";
} # end sub header_numbers()

#----------------------------------#
# Shows totals order by ocurrences #
#----------------------------------#
sub ocurrences {
    my ($total_ref, $max, $options_ref) = @_;
    # search balls not in the draw and put 0 value
    for (my $ball = 1;$ball <=$max;$ball++) {
        unless (exists($total_ref->{$ball})) {
            $total_ref->{$ball} = 0;
        }
    }
    #print ' ' x 17;
    print sprintf("  %15s ",$options_ref->{leyend});
    print $options_ref->{color}{header} unless($options{'text'});
    print ' ';
    foreach my $ball (sort { $total_ref->{$b} <=> $total_ref->{$a} or $a <=> $b} keys %{$total_ref}) {
        print sprintf("%02d",$ball) . ' ';
    }
    print RESET unless($options{'text'});
    print "\n";

    print ' ' x 18;
    print $options_ref->{color}{detail} unless($options{'text'});
    print ' ';
    foreach my $ball (sort { $total_ref->{$b} <=> $total_ref->{$a} or $a <=> $b} keys %{$total_ref}) {
        print sprintf("%2s",$total_ref->{$ball}) . ' ';
    }
    print RESET unless($options{'text'});
    print "\n";
} # End sub ocurrences()

#---------------------------#
# Shows totals of each ball #
#---------------------------#
sub totals {
    my ($total_ref,$max,$options_ref) = @_;
    print $options_ref->{color}{leyend} unless($options{'text'});
    print sprintf("%17s ",$options_ref->{leyend});
    print $options_ref->{color}{detail} unless($options{'text'});
    print ' ';
    for (my $i = 1;$i<=$max;$i++) {
         if (exists($total_ref->{$i})) {
             print sprintf("%2s ",$$total_ref{$i});
         }
         else {
             print '   ';
         }
    }
    print $options_ref->{color}{leyend} unless($options{'text'});
    print ' ';
    print RESET unless($options{'text'});
    print "\n";
} # End sub totals()

#----------------------------#
# Shows totals graph on text #
#----------------------------#
sub text_graph {
    my ($total_ref, $max, $options_ref) = @_;
    my $max_value = 0;

    # print the balls numbers
    print ' ' x 13;
    print $options_ref->{color}{balls} unless($options{'text'});
    print ' ' x 6;
    for (my $i = 1;$i<=$max;$i++) {
        #print '   ';
        print sprintf("%02d ",$i);
    }
    print ' ';
    print RESET unless($options{'text'});
    print "\n";

    # obtain the max value on totals_ref to define the axis
    $_ > $max_value and $max_value = $_ for values %{$total_ref};

    # graph on text the results
    for (my $axis = $max_value + 1; $axis >= 1; $axis--) {
        print ' ' x 13;
        print $options_ref->{color}{axis} unless($options{'text'});
        print sprintf(" %3s ", $axis);
        print RESET unless($options{'text'});
        print ' ';
        for (my $ball = 1;$ball <=$max;$ball++) {
            if (exists($total_ref->{$ball})) {
                if ($axis <= $total_ref->{$ball}) {
                    if ($options{'text'}) {
                        print ' X ';
                    }
                    else {
                        print ' ';
                        print $options_ref->{color}{bar};
                        print ' ';
                        print RESET;
                        print ' ';
                    }
                }
                else {
                    print '   ';
                }
            }
            else {
                print '   ';
            }
        }
        print $options_ref->{color}{axis} unless($options{'text'});
        print ' ';
        print RESET unless($options{'text'});
        print "\n";
    }
    # print the balls totals
    print ' ' x 13;
    print $options_ref->{color}{axis} unless($options{'text'});
    print ' ' x 5;
    print $options_ref->{color}{totals} unless($options{'text'});
    print ' ';
    for (my $i = 1;$i<=$max;$i++) {
        print sprintf("%2s ", $total_ref->{$i});
    }
    print $options_ref->{color}{axis} unless($options{'text'});
    print ' ';
    print RESET unless($options{'text'});
    print "\n";
} # End sub text_graph()

#------------------------------------------------#
# Shows and calculate totals of a given quantity #
# of draws of a lottery product                  #
#------------------------------------------------#
sub lottery {
    my $quantity = shift;
    my %totals = ();
    my %results = ();
    $quantity = 30 unless($quantity);
    if ($options{'morning'} or $options{'night'}) {
        $quantity *= 2;
    }
    my $break = 0;
    my $range = 28;

    # Search the resulst and draws of a lottery product
    my $ret = $sth_results->execute($quantity);
    while (my $results_ref = $sth_results->fetchrow_hashref) {
        if ( (($results_ref->{draw} % 2) == 0) && $options{'night'} ) {
            $results{$results_ref->{draw}}{date} = $results_ref->{date_time};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r1}} = $results_ref->{r1};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r2}} = $results_ref->{r2};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r3}} = $results_ref->{r3};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r4}} = $results_ref->{r4};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r5}} = $results_ref->{r5};
        }
        elsif ( (!($results_ref->{draw} % 2) == 0) && $options{'morning'} ) {
            $results{$results_ref->{draw}}{date} = $results_ref->{date_time};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r1}} = $results_ref->{r1};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r2}} = $results_ref->{r2};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r3}} = $results_ref->{r3};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r4}} = $results_ref->{r4};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r5}} = $results_ref->{r5};
        }
        elsif (!$options{'morning'} && !$options{'night'}) {
            $results{$results_ref->{draw}}{date} = $results_ref->{date_time};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r1}} = $results_ref->{r1};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r2}} = $results_ref->{r2};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r3}} = $results_ref->{r3};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r4}} = $results_ref->{r4};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r5}} = $results_ref->{r5};
        }
    }
    $sth_results->finish();
    # break analysis variables
    my $break_line = 0;
    my @break_array = ();
    my %break =();

    # calculate numbers and add totals
    foreach my $draw (sort { $b <=> $a } keys %results) {
        $break_line++;
        foreach my $ball  (sort keys %{$results{$draw}{balls}}) {
            if (exists($totals{$ball})) {
                $totals{$ball} += 1;
                $break{$ball}  += 1;
            }
            else {
                $totals{$ball} = 1;
                $break{$ball}  = 1;
            }
        }
        if (exists($options{'break'})) {
            $break = $options{'break'};
            if ( ($break_line % $break) == 0) {
                push (@break_array, {%break});
                %break =();
            }
            elsif ( $break_line >= scalar(keys %results)){
                push (@break_array, {%break});
                %break =();
            }
        }
    }

    # if "summary" option is in not given, print the matrix of draws and winning numbers
    unless ($options{'summary'}) {
        # Print header numbers
        header_numbers($range,\%header_numbers_options);
        # Print draws and order the numbers output
        $break_line = 0;
        my $break_count = 0;
        foreach my $draw (sort { $b <=> $a } keys %results) {
            $break_line++;
            print $matrix_options{color}{draw}  unless($options{'text'});
            print sprintf(" %05d",$draw);
            print RESET  unless($options{'text'});
            print $matrix_options{color}{date} unless($options{'text'});
            print " $results{$draw}{date} ";
            print $matrix_options{color}{detail} unless($options{'text'});
            print ' ';
            for (my $i = 1;$i<=$range;$i++) {
                if (exists($results{$draw}{balls}{$i})) {
                    print sprintf("%02d ",$results{$draw}{balls}{$i});
                }
                else {
                    print '   ';
                }
            }
            print $matrix_options{color}{draw} unless($options{'text'});
            print ' ';
            print RESET  unless($options{'text'});
            print "\n";

            if (exists($options{'break'})) {
                $break = $options{break};
                if ( ($break_line % $break) == 0) {
                    $break_options{leyend} = 'Break zone ' . ($break_count + 1);
                    totals($break_array[$break_count],$range,\%break_options);
                    $break_count++;
                }
                elsif ( $break_line >= scalar(keys %results)){
                    $break_options{leyend} = 'Break zone ' . ($break_count + 1);
                    totals($break_array[$break_count], $range, \%break_options );
                }
            }

        }
        # Print the totals of a ball occurences
        totals(\%totals,$range, \%totals_options);
        print "\n";

        # graph on text the balls ocurrences
        if (exists($options{'graph'})) {
            text_graph(\%totals,$range, \%graph_options);
            print "\n";
        }

        if (exists($options{'break'})) {
            for(my $i=0;$#break_array>=$i;$i++){
                $break_ocurrences_options{leyend} = 'Break zone ' . ($i + 1);
                ocurrences($break_array[$i],$range, \%break_ocurrences_options);
                print "\n";
            }
        }
    }

    # Print the numbers order by occurrences
    ocurrences(\%totals,$range, \%ocurrences_options);
    print "\n";

    # take a weight factor on each ball multiply the level of ocurrences
    if (exists($options{'weight'}) && exists($options{'break'})) {
        my %weight = ();
        my $level = $#break_array + 1;
        for(my $i=0;$#break_array>=$i;$i++){
            foreach my $ball (sort keys %{$break_array[$i]}) {
                if (exists($break_array[$i]->{$ball})) {
                    $weight{$ball} += ($break_array[$i]->{$ball} * $level);
                }
            }
            $level--;
        }
        ocurrences(\%weight,$range,\%weight_ocurrences_options);
        print "\n";
    }
} # End sub Lottery

#-----------#
# Main body #
#-----------#

# Process options
    if ($options{'download'}) {
    download_results();
}
lottery($options{'count'});


$dbh->disconnect;

# End Main Body #
