K debugger
==========

This is an experimental debugger for K proof run with the Haskell backend.

Running
-------

```sh
kompile semantics.k --backend haskell
kdebug kprove \
  --debugger \
  --debug-script haskell-backend/src/main/native/haskell-backend/kore/data/kast.kscript \
  my-proof.k
```

You should be able to use any command that starts kore-repl with the right
aliases (only `konfig` is needed at the time when this was written).

Shortcuts
---------

* `Tab` - switches between windows
* `Up`, `Down`, `PgUp`, `PgDn`, `Home`, `End` - navigate in the current window
* `Space` - in the tree window, collapse the current branch
* `F10` - Quit
* `F9` - Refresh the screen

Notes
-----

Only some configurations are loaded by default (e.g. the ones involved in
branching). To load a configuration you have to select it in the navigation
windows and wait for it to be loaded.
