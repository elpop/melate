# melate
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
