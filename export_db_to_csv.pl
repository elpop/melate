#!/usr/bin/perl
#======================================================================#
# Program => export_db_to_csv.pl (In Perl 5.0)           version 1.0.0 #
#======================================================================#
# Autor         => Fernando "El Pop" Romo           (pop@cofradia.org) #
# Creation date => 19/feb/2026                                         #
#----------------------------------------------------------------------#
# Info => This program export the results table from sqlite DB to CSV  #
#----------------------------------------------------------------------#
#        This code are released under the GPL 3.0 License.             #
#                                                                      #
#                     (c) 2026 - Fernando Romo                         #
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

# Command Line options
my %options = ();
GetOptions(\%options,
           'lottery=s',
           'help|?',
);

my $work_dir = $ENV{'HOME'} . '/.melate'; # keys directory
# if not exists the work directory, creates and put the init_flag on
unless (-e "$work_dir") {
    die "no db found\n";
}

# Open or create SQLite DB
my $dbh = DBI->connect("dbi:SQLite:dbname=$work_dir/melate.db","","");
$dbh->{PrintError} = 0; # Disable automatic  Error Handling

# prepare in advanced the work query
my $SQL_Code = "select * from results where product_id = ? order by draw desc;";
my $sth_results = $dbh->prepare($SQL_Code);

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
    elsif ($name eq 'retro') {
        $product = 30;
    }
    return $product;
}

#----------------------------------#
# Esxport to CSV the given product #
#----------------------------------#
sub export_to_csv {
    my ($product) = @_;
    my %totals = ();
    my %results = ();
    my $range = 0;

    # read the lottery product info
    $SQL_Code = "select * from products where id = $product;";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    # search product info
    while (my $info_ref = $sth->fetchrow_hashref) {
        print 'NPRODUCTO,CONCURSO,R1,R2,R3,R4,R5,R6,';
        print 'R7,' if ($info_ref->{additional} == 1);
        print 'BOLSA,FECHA' . "\n";
        $range = $info_ref->{range};
        # Search the resulst and draws of a lottery product
        $ret = $sth_results->execute($info_ref->{id});
        while (my $results_ref = $sth_results->fetchrow_hashref) {
            print "$product,$results_ref->{draw},";
            print "$results_ref->{r1},";
            print "$results_ref->{r2},";
            print "$results_ref->{r3},";
            print "$results_ref->{r4},";
            print "$results_ref->{r5},";
            print "$results_ref->{r6},";
            print "$results_ref->{r7}," if ($info_ref->{additional} == 1);
            print "$results_ref->{award},";
            my ($year,$month,$day) = split('-', $results_ref->{date_time});
            print sprintf("%02d\/%02d\/%04d\n", $day, $month, $year);
        }
        $sth_results->finish();
    }
    $sth->finish();

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
    my $product = search_product($options{'lottery'});
    if ($product) {
        export_to_csv($product);
    }
    else {
        print 'melate.pl -lottery [melate|revancha|revanchita|retro]' ."\n";
    }
}
else {
    print "Error: no option found\n";
}

$dbh->disconnect;

# End Main Body #

#-----------------------------------#
# Help info for use with Pod::Usage #
#-----------------------------------#
__END__

=head1 NAME

export_db_to_csv.pl

=head1 DESCRIPTION

This program export to CSV the results of Mexican melate draws "Melate", "Revancha", "Revanchita" and "Retro".

=head1 SYNOPSIS

export_db_to_csv.pl [options]

=head1 OPTIONS

=over 8

=item B<-lottery or -l>

The -lottery or -l option shows the draws and results of a given lottery name:

    export_db_to_csv.pl -lottery melate

    or

    export_db_to_csv.pl -l melate

    The values can "melate", "revancha", "revanchita" and "retro".

=item B<-help or -h or -?>

Show this help

=back

=cut
