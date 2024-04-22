# melate

## Description

Mexican version of lottery (lotto).

## Summary

```
Usage:
    melate.pl [options]

Options:
    -lottery or -l
            The -lottery or -l option show the draws and result of a given
            lottery name:

                melate.pl -lottery melate

                or

                melate.pl -l melate

                The values could be "melate", "revancha", "revanchita" and "retro".
    
                By default shows the lastes 30 draws, you can use the -count option to
                modify this behavior.

    -count or -c
            Show the last number of draws of a given lottery name:

                melate.pl -lottery melate -count 20

                or

                melate.pl -l melate -c 20

    -totals or -t
            Used with the -lottery (or -l) option, Don't show the draws an
            numbers matriz, only the totals of the analysis:

                melate.pl -lottery melate -count 20 -totals

                or

                melate.pl -l melate -c 20 -t

    -download or -d
            Download the results of draws of lottery products from the
            lottery authority and insert into the sqlite DB:

                melate.pl -download

                or

                melate.pl -d

                the operation could take a while.

    -awards or -a
            Search the last award information of each lottery product

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

    -help or -h or -?
            Show this help
```
## Install

1. Download file
  
    ```
    git clone https://github.com/elpop/melate.git
    ```  

2. Install SQLite:

   The programs use SQLite. This is available for default in Mac OS and the most popular Linux distros.
   
    for Debian/Ubuntu Linux systems:
    
    ```
    sudo apt-get install sqlite3 libsqlite3-dev
    ```
    
    Fedora/Red-Hat Linux systems:
    
    ```
    sudo dnf install sqlite sqlite-devel 
    ```
    
3. Perl Dependencies
    
    [File::Copy](https://metacpan.org/pod/File::Copy)
    
    [Text::Diff](https://metacpan.org/pod/Text::Diff)
    
    [Getopt::Long](https://metacpan.org/pod/Getopt::Long)
    
    [Pod::Usage](https://metacpan.org/pod/Pod::Usage)

    [DBI](https://metacpan.org/pod/DBI)

    [DBD::SQLite](https://metacpan.org/pod/DBD::SQLite)

    All the Perl Moules are available via [metacpan](https://metacpan.org) or install via "cpan" program in your system. Debian/Ubuntu and Fedora has packages for the perl modules.
    
4. Put on your search path
    
    Copy the ga_cli.pl program somewhere in your search path:
    
    ```
    cp melate.pl /usr/local/bin/.
    ```
    
## Initial run

the program create a hidden directory ".melate" in your HOME path.

into th directory create the sqlite DB called "melate.db" and a results directory for process the files from the lottery authority.

when you run for the firs time you see the following:

```
    Init DB
    Download results from Pronosticos Deportivos
    Melate
    Revancha
    Revanchita
    Melate Retro
    Error: no option found
```

     
Now, you can use the program, you can update the results database with the -dowload option.


