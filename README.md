# rtl-comrade

## Log classification

DEBUG / INFO  = normal observability
STATUS        = transient user-facing progress
WARNING       = important but does not fail the run
ERROR         = run has failed, but execution is allowed to continue
CRITICAL      = run has failed and execution is forced to terminate immediately

Log event fields may contain rich Python objects. Renderers are responsible for converting them into displayable output. Machine-oriented renderers should normalize or summarize rich objects at the boundary.
