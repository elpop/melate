#!/usr/bin/perl
#=====================================================================#
# Program => melate.pl (In Perl 5.0)                    version 1.0.0 #
#=====================================================================#
# Autor         => Fernando "El Pop" Romo          (pop@cofradia.org) #
# Creation date => 22/April/2024                                      #
#---------------------------------------------------------------------#
# Info => This program gives statistical information of the numbers   #
#         of the mexican version of lotto.                            #
#---------------------------------------------------------------------#
# This code are released under the GPL 3.0 License. Any change must   #
# be report to the authors                                            #
#                     (c) 2024 - Fernando Romo                        #
#=====================================================================#
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

    BG_BLACK    => "\033[40m",
    BG_RED      => "\033[41m",
    BG_GREEN    => "\033[42m",
    BG_YELLOW   => "\033[43m",
    BG_BLUE     => "\033[44m",
    BG_MAGENTA  => "\033[45m",
    BG_CYAN     => "\033[46m",
    BG_WHITE    => "\033[47m",
};

# Command Line options
my %options = ();
GetOptions(\%options,
           'lottery=s',
           'count=i',
           'download',
           'summary',
           'text',
           'awards',
           'help|?',
);

my $init_flag = 0;

my $work_dir = $ENV{'HOME'} . '/.melate'; # keys directory
# if not exists the work directory, creates and put the init_flag on
unless (-e "$work_dir") {
    mkdir($work_dir);
    $init_flag = 1;
}

#locate wget on your system
my ($wget) = qx(/usr/bin/which wget);
chomp($wget);

my $dbh = DBI->connect("dbi:SQLite:dbname=$work_dir/melate.db","","");
$dbh->{PrintError} = 0; # Disable automatic  Error Handling

# if not exists the db schema, creates and star a initial load of the results
if ($init_flag) {
    # init the db schema
    init_db();
}

# prepare in advanced the read results query
my $SQL_Code = "select * from results where product_id = ? order by draw desc limit ?;";
my $sth_results = $dbh->prepare($SQL_Code);

$SQL_Code = "select product_id, draw from results where product_id = ? and draw = ?;";
my $sth_read = $dbh->prepare($SQL_Code);

$SQL_Code = "insert into results(product_id, draw, date_time, r1, r2, r3, r4, r5, r6, r7, award)
                            values( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? );";
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
    # Create lottery products Table
    $SQL_Code = "CREATE TABLE products (
            id         integer not null,
            name       text not null,
            range      integer not null,
            balls      integer not null,
            additional integer not null,
            url        text not null,
            filename   text not null
        );";
    $dbh->do($SQL_Code);
    # Create index on products table
    $SQL_Code = "CREATE UNIQUE INDEX un_p_id on products(id);";
    $dbh->do($SQL_Code);
    # Insert Initial info of lottery draws
    $SQL_Code = "INSERT INTO products(id, name, range, balls, additional, url, filename) VALUES(40,'Melate',56,6,1,'https://pronosticos.gob.mx/Documentos/Historicos/Melate.csv','Melate');";
    $dbh->do($SQL_Code);
    $SQL_Code = "INSERT INTO products(id, name, range, balls, additional, url, filename) VALUES(41,'Revancha',56,6,0,'https://www.pronosticos.gob.mx/Documentos/Historicos/revancha.csv','Revancha');";
    $dbh->do($SQL_Code);
    $SQL_Code = "INSERT INTO products(id, name, range, balls, additional, url, filename) VALUES(34,'Revanchita',56,6,0,'https://www.pronosticos.gob.mx/Documentos/Historicos/Revanchita.csv','Revanchita');";
    $dbh->do($SQL_Code);
    $SQL_Code = "INSERT INTO products(id, name, range, balls, additional, url, filename) VALUES(30,'Melate Retro',39,6,1,'https://pronosticos.gob.mx/Documentos/Historicos/Melate-Retro.csv','Retro');";
    $dbh->do($SQL_Code);
    # Create the results table of the lottery draw
    $SQL_Code = "
        CREATE TABLE results (
            id         INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            draw       integer NOT NULL,
            date_time  TEXT    NOT NULL,
            r1         integer,
            r2         integer,
            r3         integer,
            r4         integer,
            r5         integer,
            r6         integer,
            r7         integer,
            award      integer,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );";
    $dbh->do($SQL_Code);
    # Create index on results table
    $SQL_Code = "CREATE UNIQUE INDEX un_pi_d_results ON results(product_id, draw);";
    $dbh->do($SQL_Code);
    $SQL_Code = "CREATE INDEX in_dt_results on results(date_time);";
    $dbh->do($SQL_Code);
    $SQL_Code = "CREATE INDEX in_draw_results on results(draw);";
    $dbh->do($SQL_Code);
} # End sub init_db()

#--------------------------------------#
# Search if the record already exists  #
#--------------------------------------#
sub already_on_results {
    my ($product, $draw) = @_;
    my $already = 0;
    my $ret = $sth_read->execute($product,$draw);
    while (my $read_ref = $sth_read->fetchrow_hashref) {
        $already++;
    }
    $sth_read->finish();
    return $already
} # en sub _already_on_results()

#----------------------------------------------#
# Show the amount of awards of a given product #
#----------------------------------------------#
sub prize {
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
}

#-------------------------------------------#
# Show the amount of awards of each lottery #
#-------------------------------------------#
sub awards {
    # Read each lottery name
    $SQL_Code = "select id, name from products;";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    while (my $info_ref = $sth->fetchrow_hashref) {
        print "$info_ref->{name}\n";
        print sprintf("    %s, %s, %s\n",prize($info_ref->{id}) );
    }
    $sth->finish();
} # End sub awards()

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
    );
    $ua->ssl_opts(verify_hostname => 0);
    $| = 1;         # autoflush
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
}

#-----------------------------------------------#
# Download the files from the lottery authority #
# and insert the new results into the SQLite DB #
#-----------------------------------------------#
sub download_results {
    print "Download results from Pronosticos Deportivos\n";

    # check if exists the work directory
    unless (-e "$work_dir/results") {
        mkdir("$work_dir/results");
        open(TOUCH, ">", "$work_dir/results/Melate.csv") or die;
        close(TOUCH);
        open(TOUCH, ">", "$work_dir/results/Revancha.csv") or die;
        close(TOUCH);
        open(TOUCH, ">", "$work_dir/results/Revanchita.csv") or die;
        close(TOUCH);
        open(TOUCH, ">", "$work_dir/results/Retro.csv") or die;
        close(TOUCH);
    }

    # Read each lottery information
    my $SQL_Code = "select * from products;";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    while (my $products_ref = $sth->fetchrow_hashref) {
        print "$products_ref->{name}\n";
        # move working files
        move("$work_dir/results/$products_ref->{filename}.csv", "$work_dir/results/$products_ref->{filename}.old");
        # download with LWP::UserAgent, is faster than wget
        my $process_flag = 0;
        $process_flag = eval { get_file($products_ref->{url},"$work_dir/results/$products_ref->{filename}.csv") };
        if ($process_flag) {
            # obtain only the difference of record to process
            my $diff = diff( "$work_dir/results/$products_ref->{filename}.old", "$work_dir/results/$products_ref->{filename}.csv");
            my @changes = $diff =~ /\+(\d\d,.*?)\n/g;
            # process each result and insert into the results table
            foreach my $new (sort { $a <=> $b } @changes) {
                if ($products_ref->{additional} == 1) {
                    my ($prod,$sorteo,$r1,$r2,$r3,$r4,$r5,$r6,$r7,$acum,$fecha) = split(/,/,$new);
                    my ($day, $month, $year) = split(/\//,$fecha);
                    my $date_time = sprintf("%04d-%02d-%02d",$year, $month, $day);
                    # insert the new record if not previously exists
                    unless( already_on_results($prod, $sorteo) ) {
                        print "    $prod,$sorteo,$date_time, $r1,$r2,$r3,$r4,$r5,$r6,$r7,$acum\n" unless($init_flag);
                        $sth_insert->execute($prod,$sorteo,$date_time, $r1,$r2,$r3,$r4,$r5,$r6,$r7,$acum);
                    }
                }
                else {
                    my ($prod,$sorteo,$r1,$r2,$r3,$r4,$r5,$r6,$acum,$fecha) = split(/,/,$new);
                    my ($day, $month, $year) = split(/\//,$fecha);
                    my $date_time = sprintf("%04d-%02d-%02d",$year, $month, $day);
                    unless( already_on_results($prod, $sorteo) ) {
                        print "    $prod,$sorteo,$date_time, $r1,$r2,$r3,$r4,$r5,$r6,$acum\n" unless($init_flag);
                        # insert the new record if not previously exists
                        $sth_insert->execute($prod,$sorteo,$date_time, $r1,$r2,$r3,$r4,$r5,$r6,'',$acum);
                    }
                }
            }
            # remove old file
            unlink("$work_dir/results/$products_ref->{filename}.old");

        }
        else {
            move("$work_dir/results/$products_ref->{filename}.old", "$work_dir/results/$products_ref->{filename}.csv");
            print "Error: Problem downloading file from $products_ref->{url}\n";
        }
    }
    $sth->finish();
} # end sub download_results()

#------------------------------------------------#
# Shows and calculate totals of a given quantity #
# of draws of a lottery product                  #
#------------------------------------------------#
sub lottery {
    my ($product, $quantity) = @_;
    my %totals = ();
    my %results = ();
    $product = 40 unless($product);
    $quantity = 30 unless($quantity);
    my $nummax = 0;

    # read the lottery product info
    $SQL_Code = "select * from products where id = $product;";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    my ($draw, $date, $prize) = prize($product);
    while (my $info_ref = $sth->fetchrow_hashref) {
        $nummax = $info_ref->{range};
        # print general lottery info;
        print BG_RED . FG_WHITE . BRIGHT unless($options{'text'});
        print "Product: $info_ref->{name}     Date: $date    Prize: $prize    Samples: $quantity ";
        print RESET unless($options{'text'});
        print "\n";
        # Search the resulst and draws of a lottery product
        $ret = $sth_results->execute($info_ref->{id},$quantity);
        while (my $results_ref = $sth_results->fetchrow_hashref) {
            $results{$results_ref->{draw}}{date} = $results_ref->{date_time};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r1}} = $results_ref->{r1};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r2}} = $results_ref->{r2};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r3}} = $results_ref->{r3};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r4}} = $results_ref->{r4};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r5}} = $results_ref->{r5};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r6}} = $results_ref->{r6};
            $results{$results_ref->{draw}}{balls}{$results_ref->{r7}} = $results_ref->{r7} if ($info_ref->{additional} == 1);
        }
        $sth_results->finish();
    }
    $sth->finish();

    # search numbers and add totals
    foreach my $draw  (sort { $results{$b} <=> $results{$a} }keys %results) {
        foreach my $ball  (sort keys %{$results{$draw}{balls}}) {
            if (exists($totals{$ball})) {
                $totals{$ball} = $totals{$ball} + 1;
            }
            else {
                $totals{$ball} = 1;
            }
        }
    }
    
    # search balls not in the draw and put 0 value
    for (my $ball = 1;$ball <=$nummax;$ball++) {
        unless (exists($totals{$ball})) {
            $totals{$ball} = 0;
        }
    }

    # if "summary" option is in not given, print the matrix of draws and winning numbers
    unless ($options{'summary'}) {
        # Print header numbers
        my $x_rep = (3 * $nummax) +5;
        print BG_WHITE . BRIGHT . FG_BLACK unless($options{'text'});
        print '  #     Date     ';
        for (my $i = 1;$i<=$nummax;$i++) {
            print sprintf("%02d ",$i);
        }
        print RESET unless($options{'text'});
        print "\n";

        # Print draws and order the numbers output
        foreach my $draw (sort { $b <=> $a } keys %results) {
            print BG_WHITE . BRIGHT .FG_BLACK unless($options{'text'});
            print sprintf("%04d",$draw);
            print RESET  unless($options{'text'});
            print BG_WHITE . FG_BLACK unless($options{'text'});
            print " $results{$draw}{date} ";
            print RESET  unless($options{'text'});
            print ' ';
            #        foreach my $num (sort { $a <=> $b } keys %{$res{$sorteo}}) {
            for (my $i = 1;$i<=$nummax;$i++) {
                if (exists($results{$draw}{balls}{$i})) {
                    print sprintf("%02d ",$results{$draw}{balls}{$i});
                }
                else {
                    print '   ';
                }
            }
            print "\n";
        }
        # Print the occurrence of a number
        print BG_WHITE . BRIGHT . FG_BLACK  unless($options{'text'});
        print '                 ';
        for (my $i = 1;$i<=$nummax;$i++) {
             if (exists($totals{$i})) {
                 print sprintf("%02d ",$totals{$i});
             }
             else {
                 print '   ';
             }
        }
        print RESET unless($options{'text'});
        print "\n\n";
    }
     
    # Print the numbers order by occurrences
    my $aux = 0;
    print FG_GREEN  unless($options{'text'});
    foreach my $ball (sort { $totals{$b} <=> $totals{$a} or $a <=> $b} keys %totals) {
        if ( $aux ne $totals{$ball} ) {
            print '  ';
            $aux = $totals{$ball};
        }
        print sprintf("%02d",$ball) . ' ';
    }
    print RESET unless($options{'text'});
    print "\n";
    print FG_YELLOW unless($options{'text'});
    $aux = 0;
    foreach my $ball (sort { $totals{$b} <=> $totals{$a} or $a <=> $b} keys %totals) {
        if ( $aux ne $totals{$ball} ) {
            print '  ';
            $aux = $totals{$ball};
        }
        print sprintf("%02d",$totals{$ball}) . ' ';
    }
    print RESET unless($options{'text'});
    print "\n\n";
} # End sub Lottery

#-----------#
# Main body #
#-----------#

# Process options
if ($options{'help'}) {
    pod2usage(-exitval => 0, -verbose => 1);
    pod2usage(2);
}
elsif ($options{'lottery'}) {
    my $product = 0;
    if ($options{'lottery'} eq 'melate') {
        $product = 40;
    }
    elsif ($options{'lottery'} eq 'revancha') {
        $product = 41;
    }
    elsif ($options{'lottery'} eq 'revanchita') {
        $product = 34;
    }
    elsif ($options{'lottery'} eq 'retro') {
        $product = 30;
    }
    if ($product) {
        lottery($product,$options{'count'});
    }
    else {
        print 'melate.pl -lottery [melate|revancha|revanchita|retro]' ."\n";
    }
}
elsif ($options{'download'}) {
    download_results();
}
elsif ($options{'awards'}) {
    awards();
}
else {
    print "Error: no option found\n" unless($init_flag);
}

$dbh->disconnect;

# End Main Body #

#-----------------------------------#
# Help info for use with Pod::Usage #
#-----------------------------------#
__END__

=head1 NAME

melate.pl

=head1 DESCRIPTION

This program report the results of Mexican lotto draws "Melate", "Revancha", "Revanchita" and "Retro".

=head1 SYNOPSIS

melate.pl [options]

=head1 OPTIONS

=over 8

=item B<-lottery or -l>

The -lottery or -l option shows the draws and results of a given lottery name:

    melate.pl -lottery melate

    or

    melate.pl -l melate

    The values can "melate", "revancha", "revanchita" and "retro".

    By default shows the lastest 30 draws, you can use the -count option to
    modify this behavior.

=item B<-count or -c>

Show the last N number of draws of a given lottery name:

    melate.pl -lottery melate -count 20

    or

    melate.pl -l melate -c 20

=item B<-download or -d>

Download the results of draws of lottery products from the lottery authority
and insert them into the sqlite DB:

    melate.pl -download

    or

    melate.pl -d

    the operation could take a while.

=item B<-awards or -a>

Search for the last award information of each lottery product

    melate.pl -award

    or

    melate.pl -a

And show (for example):

    Melate
        3890, 2024-04-21, $202,500,000.00
    Revancha
        3890, 2024-04-21, $97,900,000.00
    Revanchita
        3890, 2024-04-21, $330,600,000.00
    Melate Retro
        1418, 2024-04-20, $5,100,000.00

=item B<-summary or -s>

Used with the -lottery (or -l) option. Don't show the draws and numbers matrix,
only the summary of the analysis:

    melate.pl -lottery melate -count 20 -summary

    or

    melate.pl -l melate -c 20 -s

=item B<-text or -t>

Used with the -lottery (or -l) option. Don't show terminal text color.

Use this to make printable output or generate files without escape codes.

    melate.pl -lottery melate -count 20 -text

    or

    melate.pl -l melate -c 20 -t

    you can write a bash script to send the print output to file:

        #!/bin/bash
        PRODUCT="melate revancha revanchita retro"
        NUMBER="20 10"
        for prod in $PRODUCT
        do
            for count in $NUMBER
            do
                /usr/local/bin/melate.pl -l $prod -c $count -t > $prod"_"$count.log
            done
        done

=item B<-help or -h or -?>

Show this help

=back

=cut
