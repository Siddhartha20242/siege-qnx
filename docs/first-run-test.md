# Try Siege for ten minutes and tell us where it hurt

Siege has been run end to end only by its author, so the first-run experience is
untested by anyone else. If you are willing to be that person, this page is the
whole job. You do not need QNX for the first part.

## Part 1: no install (about five minutes)

You need Python 3. Write down the time you start.

```sh
git clone https://github.com/Siddhartha20242/siege-qnx && cd siege-qnx
./siege show            # the measured results as a table
./siege show secpol     # the security-policy runs
./siege list            # what can be run
./siege doctor          # what your machine is missing, and the first thing to fix
./siege frontier replay # optional, needs numpy, about a minute
```

## Part 2: only if you have QNX SDP 8.0 (about fifteen minutes plus the build)

```sh
./siege doctor
./siege setup user@host   # skip if the SDP is loaded in your shell
./siege build
./siege live              # pick "workflood @prio 30", press Run
```

## What to send back

Open an issue at https://github.com/Siddhartha20242/siege-qnx/issues/new/choose with the "I tried Siege" template, or reply wherever you found this.
Please include:

1. Your machine (Mac or PC, chip, OS) and whether you had QNX.
2. How far you got, and how long each part took.
3. The first place you were unsure what to do, with the command or sentence involved.
4. Anything the README promised that did not happen.
5. A score from 1 to 10 for "I could get a result without help", and one change that would raise it.

A "this confused me" report is exactly as useful as a "this worked" report, and
both will be quoted, with your permission, in the project's notes.
