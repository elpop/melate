#!/usr/bin/perl
#======================================================================#
# Program => download_results.pl (In Perl 5.0)           version 1.0.0 #
#======================================================================#
# Autor         => Fernando "El Pop" Romo           (pop@cofradia.org) #
# Creation date => 22/feb/2026                                         #
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
use LWP::UserAgent; # Web user agent class
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

#--------------------------------------#
# Search the download parameters on DB #
#--------------------------------------#
sub download {
    my $product = shift;
    my $SQL_Code = "select url, filename from products where id = $product;";
    my $sth = $dbh->prepare($SQL_Code);
    my $ret = $sth->execute();
    while (my $products_ref = $sth->fetchrow_hashref) {
        # download with LWP::UserAgent, is faster than wget
        eval { get_file($products_ref->{url},"$products_ref->{filename}.csv") };
    }
    $sth->finish();
}

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
        download($product);
    }
    else {
        print 'download_results.pl -lottery [melate|revancha|revanchita|retro]' ."\n";
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

download_results.pl

=head1 DESCRIPTION

This program export to CSV the results of Mexican melate draws "Melate", "Revancha", "Revanchita" and "Retro".

=head1 SYNOPSIS

download_results.pl [options]

=head1 OPTIONS

=over 8

=item B<-lottery or -l>

The -lottery or -l option shows the draws and results of a given lottery name:

    download_results.pl -lottery melate

    or

    download_results.pl -l melate

    The values can "melate", "revancha", "revanchita" and "retro".

=item B<-help or -h or -?>

Show this help

=back

=cut
