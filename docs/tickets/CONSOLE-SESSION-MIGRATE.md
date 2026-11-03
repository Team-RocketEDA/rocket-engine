Follow-up to the CONSOLE-APPLY retire commit: ConsoleSession
(console/session.py) is still the live approval-bound cell surface
used by lifecycle.py and stdio_console.py, while ApplySession is the
new atomic host-side context. Migrate the session cell path onto
ApplySession (behavioral slice: worker replay, approvals binding,
lifecycle status), then remove session.py. Needs its own RED first.
