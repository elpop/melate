# melate

## Description

A Mexican version of lottery (lotto) and it can easily be modified to accommodate other local lotteries.

![light panel](https://raw.githubusercontent.com/elpop/melate/master/melate.png)

## Summary

```
Usage:
    melate.pl [options]

Options:
    -lottery or -l
            The -lottery or -l option shows the draws and results of a given
            lottery name:

                melate.pl -lottery melate

                or

                melate.pl -l melate

                The values can be "melate", "revancha", "revanchita" and "retro".
    
                By default shows the latest 30 draws, you can use the -count option to
                modify this behavior.

    -count or -c
            Show the last N number of draws of a given lottery name:

                melate.pl -lottery melate -count 20

                or

                melate.pl -l melate -c 20

    -download or -d
            Download the results of draws of lottery products from the
            lottery authority and insert them into a sqlite DB:

                melate.pl -download

                or

                melate.pl -d

                the operation could take a while.

    -awards or -a
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

    -summary or -s
            Used with the -lottery (or -l) option. Don't show the draws and
            numbers matrix, only the summary of the analysis:

                melate.pl -lottery melate -count 20 -summary

                or

                melate.pl -l melate -c 20 -s

    -text or -t
            Used with the -lottery (or -l) option. Don't show terminal text
            color.

            Use this to make printable output or generate files without escape
            codes.

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

    -help or -h or -?
            Show this help
```

## Install

1. Download file
  
    ```
    git clone https://github.com/elpop/melate.git
    ```  

2. Install SQLite:

   The programs use SQLite. This is available for Mac OS and the most popular Linux distros.
   
    for Debian/Ubuntu Linux systems:
    
    ```
    sudo apt-get install sqlite3 libsqlite3-dev
    ```
    
    Fedora/Red-Hat Linux systems:
    
    ```
    sudo dnf install sqlite sqlite-devel
    ```
    
    Mac OS
    
    SQLite is available by default. 
    
3. Perl Dependencies
    
    [File::Copy](https://metacpan.org/pod/File::Copy)
    
    [Text::Diff](https://metacpan.org/pod/Text::Diff)
    
    [Getopt::Long](https://metacpan.org/pod/Getopt::Long)
    
    [Pod::Usage](https://metacpan.org/pod/Pod::Usage)

    [DBI](https://metacpan.org/pod/DBI)

    [DBD::SQLite](https://metacpan.org/pod/DBD::SQLite)

    [LWP::UserAgent](https://metacpan.org/pod/LWP::UserAgent)

    All the Perl Modules are available via [metacpan](https://metacpan.org) or install them via the "cpan" program in your system. Debian/Ubuntu and Fedora have packages for the required perl modules.
    
    for Fedora/Redhat:
    
    ```
    sudo dnf install perl-File-Copy perl-Text-Diff perl-Getopt-Long perl-Pod-Usage perl-DBI perl-DBD-SQLite perl-libwww-perl perl-LWP-Protocol-https
    ```
    
    for Debian/Ubuntu:
    
    ```
    sudo apt-get install libdbi-perl libdbd-sqlite3-perl libtext-diff-perl libwww-perl liblwp-protocol-https-perl
    sudo cpan -i Getopt::Long Pod::Usage
    ```
    
    On Mac OS:

    To compile some Perl modules, you need to install the 
    Xcode Command Line Tools:
 
    ```
    xcode-select --install
    ```

    Install with CPAN:
    
    ```
    sudo cpan -i File::Copy Text::Diff Getopt::Long Pod::Usage DBI DBD::SQLite LWP::UserAgent LWP::Protocol::https
    ```
    
4. Put it on your search path
    
    Copy the melate.pl program somewhere in your search path:
    
    ```
    sudo cp melate.pl /usr/local/bin/.
    ```
    
## Initial run

The program create a hidden directory ".melate" in your HOME path.

Into the directory create the sqlite DB called "melate.db" and a results directory for processing the files from the lottery authority.

when you run it for the first time you see the following:

```
    Init DB
    Download results from Pronosticos Deportivos
    Melate
    Revancha
    Revanchita
    Melate Retro
```

     
Now, you can use the program :)

You can update the results database with the -dowload option.

## Crontab to update  results

If you want to auto update the lottery results, edit your crontab and add:

```
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 8 * * 1,3,4,6,0 /usr/local/bin/melate.pl -d
```

This will run at 8 o'clock on Monday, Wednesday, Thursday, Saturday, and Sunday.

The "Melate", "Revancha" and "Revanchita" results are available on Thursday, Saturday and Monday.

"Retro" has results available on  Wednesday and Sunday.

## If you win...

Please [sponsor this project](https://github.com/sponsors/elpop), or send a big tip to pay my high debt on credit cards :)

