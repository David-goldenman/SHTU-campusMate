#ifndef PythonBridge_h
#define PythonBridge_h

/// Boots the embedded CPython and runs `boot.py`, which serves the bundled web
/// directory on 127.0.0.1. Blocks for the lifetime of the process, so it must be
/// called from a dedicated background thread. Returns a non-zero code when the
/// interpreter or the script fails to start.
int cm_start_python(const char *home, const char *script, const char *port_file,
                    const char *executable, const char *log_path);

#endif /* PythonBridge_h */
