#!/usr/bin/perl
#======================================================================#
# Program => matrix.pl (In Perl 5.0)                     version 1.0.0 #
#======================================================================#
# Autor         => Fernando "El Pop" Romo           (pop@cofradia.org) #
# Creation date => 28/August/2024                                      #
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
use Getopt::Long;   # Handle the arguments passed to the program
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
                                   'detail' => BG_BLACK . BRIGHT . FG_WHITE,
                                   'one'    => BG_BLACK . BRIGHT . FG_WHITE,
                                   'two'    => BG_BLACK . BRIGHT . FG_BRIGHT_GREEN,
                                   'three'  => BG_BLACK . BRIGHT . FG_BRIGHT_RED, }, );

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
           'summary',
           'graph',
           'break=i',
           'text',
           'weight',
           'help|?',
);


my $init_flag = 0;

my $work_dir = $ENV{'HOME'} . '/.melate'; # keys directory
# if not exists the work directory, creates and put the init_flag on
unless (-e "$work_dir") {
    mkdir($work_dir);
    $init_flag = 1;
}

# Open or create SQLite DB
my $dbh = DBI->connect("dbi:SQLite:dbname=$work_dir/melate.db","","");
$dbh->{PrintError} = 0; # Disable automatic  Error Handling

# prepare in advanced the work query
my $SQL_Code = "select * from results where product_id = ? order by draw desc limit ?;";
my $sth_results = $dbh->prepare($SQL_Code);

$SQL_Code = "select product_id, draw from results where product_id = ? and draw = ?;";
my $sth_read = $dbh->prepare($SQL_Code);

#----------------------------------------------#
# Show the amount of awards of a given product #
#----------------------------------------------#
sub get_prize {
    my $product = shift;
    my $draw  = ''; 
    my $date  = ''; 
    my $prize = ''; 

    # makes more friendly format
    sub _Money {
        my $number = shift;
        $number = sprintf("%.2".'f', $number);
        1 while $number =~ s/^(-?\d+)(\d\d\d)/$1,$2/;
        $number =~ s/^(-?)/$1\$/;
        return $number;
    } # End sub _Money()
    
    my $ret = $sth_results->execute($product,1);
    while (my $results_ref = $sth_results->fetchrow_hashref) {
        $draw  = $results_ref->{draw};
        $date  = $results_ref->{date_time};
        $prize = _Money($results_ref->{award});
    }
    $sth_results->finish();
    return $draw, $date, $prize;
} # sub prize() 

#----------------------------------#
# find product_id base on his name #
#----------------------------------#
sub search_product {
    my $name = shift;
    my $product = 0;
    if ($name eq 'melate') {
        $product = 40;
    }
    elsif ($name eq 'revancha') {
        $product = 41;
    }
    elsif ($name eq 'revanchita') {
        $product = 34;
    }
    return $product;
}

#---------------------#
# Shows balls numbers #
#---------------------#
sub header_numbers {
    my ($range, $options_ref) = @_;
        my $x_rep = (3 * $range) +5;
        print $options_ref->{color} unless($options{'text'});
        print '   #     Date     ';
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
    print sprintf(" %15s ",$options_ref->{leyend});
    print $options_ref->{color}{header} unless($options{'text'});
    print ' ';
    foreach my $ball (sort { $total_ref->{$b} <=> $total_ref->{$a} or $a <=> $b} keys %{$total_ref}) {
        print sprintf("%02d",$ball) . ' ';
    }
    print RESET unless($options{'text'});
    print "\n";

    print ' ' x 17;
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
    print sprintf("%16s ",$options_ref->{leyend});
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
    print ' ' x 12;
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
        print ' ' x 12;
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
    print ' ' x 12;
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

#--------------------#
# Shows product info #
#--------------------#
sub lottery_info {
    my ($name, $date, $prize, $samples, $options_ref) = @_;
    print $options_ref->{color} unless($options{'text'});
    print sprintf("Product: %-10s  Date: %10s  Prize: %16s Samples: %-4d ", $name, $date, $prize, $samples);
    print RESET unless($options{'text'});
    print "\n";
} # end sub lottery_info()

#------------------------------------------------#
# Shows and calculate totals of a given quantity #
# of draws of a lottery product                  #
#------------------------------------------------#
sub lottery {
    my $quantity = shift;
    my %totals = ();
    my %results = ();
    $quantity = 30 unless($quantity);
    my $break = 0;
    my $range = 0;

    # read the lottery product info
    $SQL_Code = "select * from products where id in(40,41,34);";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    # search product info
    while (my $info_ref = $sth->fetchrow_hashref) {
        $range = $info_ref->{range};
        # obtain draw info
        my ($draw, $date, $prize) = get_prize($info_ref->{id});
        # print general lottery info
        lottery_info($info_ref->{name}, $date, $prize, $quantity, \%lottery_info_options);
        my $char = '';
        if ($info_ref->{id} == 41) {
            $char = 'R';
        }
        elsif ($info_ref->{id} == 34) {
            $char = 'r';
        }
        else {
            $char = 'M';
        }
        # Search the resulst and draws of a lottery product
        $ret = $sth_results->execute($info_ref->{id},$quantity);
        while (my $results_ref = $sth_results->fetchrow_hashref) {
            $results{$results_ref->{draw}}{date} = $results_ref->{date_time};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r1}} .= $char; #$results_ref->{r1};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r2}} .= $char; #$results_ref->{r2};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r3}} .= $char; #$results_ref->{r3};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r4}} .= $char; #$results_ref->{r4};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r5}} .= $char; #$results_ref->{r5};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r6}} .= $char; #$results_ref->{r6};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r7}} .= $char if ($info_ref->{additional} == 1);
        }
        $sth_results->finish();
    }
    $sth->finish();

    # break analysis variables
    my $break_line = 0;
    my @break_array = ();
    my %break =();

    # calculate numbers and add totals
    foreach my $draw (sort { $b <=> $a } keys %results) {
        $break_line++;
        foreach my $ball  (sort keys %{$results{$draw}{balls}}) {
            if (exists($totals{$ball})) {                
                $totals{$ball} += length($results{$draw}{balls}{$ball});
                $break{$ball}  += length($results{$draw}{balls}{$ball});
            }
            else {
                $totals{$ball} = length($results{$draw}{balls}{$ball});
                $break{$ball}  = length($results{$draw}{balls}{$ball});
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
            print sprintf(" %04d",$draw);
            print RESET  unless($options{'text'});
            print $matrix_options{color}{date} unless($options{'text'});
            print " $results{$draw}{date} ";
            print $matrix_options{color}{detail} unless($options{'text'});
            print ' ';
            for (my $i = 1;$i<=$range;$i++) {
                if (exists($results{$draw}{balls}{$i})) {
                    my $len = length("$results{$draw}{balls}{$i}");
                    if ( $len == 2 ) {
                        print $matrix_options{color}{two}  unless($options{'text'});
                    }
                    elsif ( $len == 3 ){
                        print $matrix_options{color}{three}  unless($options{'text'});
                    }
                    else {
                        print $matrix_options{color}{one}  unless($options{'text'}); 
                    }
                    print sprintf("%-3s",$results{$draw}{balls}{$i});
                    print $matrix_options{color}{one}  unless($options{'text'});
                    #print RESET  unless($options{'text'});
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
if ($options{'help'}) {
    pod2usage(-exitval => 0, -verbose => 1);
    pod2usage(2);
}
else {
    lottery($options{'count'});
}

$dbh->disconnect;

# End Main Body #

#-----------------------------------#
# Help info for use with Pod::Usage #
#-----------------------------------#
__END__

=head1 NAME

matrix.pl

=head1 DESCRIPTION

This program report the results of Mexican melate draws "Melate", "Revancha", "Revanchita".

=head1 SYNOPSIS

matrix.pl [options]

=head1 OPTIONS

=over 8

=item B<-count or -c>

Show the last N number of draws of a "Melate", "Revancha", "Revanchita" an his counts

    matrix.pl -count 20

    or

    matrix.pl -c 20

=item B<-break or -b>

break on N number of draws of a "Melate", "Revancha", "Revanchita" for further analysis:

    matrix.pl -count 20 -break 10

    or

    matrix.pl -c 20 -b 10

=item B<-weight or -w>

Work with the -break option.

try to analyze each break segment, asign a weight value
for each segment (This is a experimental feature).

The most recent segments has more value than the old ones.

The sum of this values create a total weight factor to show
the posible numbers in a future draw

    matrix.pl -count 60 -break 10 -weight

    or

    matrix.pl -c 60 -b 10 -w

=item B<-graph or -g>

Create a bar chart on text of the ocurrences of each ball:

    matrix.pl -count 20 -g

    or

    matrix.pl -c 20 -g

=item B<-summary or -s>

Don't show the draws and numbers matrix, only the summary of the analysis:

    matrix.pl -count 20 -summary

    or

    matrix.pl -c 20 -s

=item B<-text or -t>

Don't show terminal text color.

Use this to make printable output or generate files without escape codes.

    matrix.pl -count 20 -text

    or

    matrix.pl -c 20 -t

=item B<-help or -h or -?>

Show this help

=back

=cut
