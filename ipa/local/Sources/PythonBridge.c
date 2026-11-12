#include "PythonBridge.h"

#include <Python/Python.h>
#include <stdio.h>

int cm_start_python(const char *home, const char *script, const char *port_file,
                    const char *executable, const char *log_path) {
    FILE *log = fopen(log_path, "w");
    if (log == NULL) {
        return 9;
    }
    fprintf(log, "bridge: home=%s\nbridge: script=%s\nbridge: executable=%s\n", home, script, executable);
    fflush(log);

    PyStatus status;
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.parse_argv = 0;
    config.install_signal_handlers = 0;
    config.write_bytecode = 0;
    config.use_environment = 0;

    status = PyConfig_SetBytesString(&config, &config.home, home);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 11;
    }

    // importlib resolves the .fwork framework paths against dirname(sys.executable),
    // so it must be the binary at the root of the app bundle.
    status = PyConfig_SetBytesString(&config, &config.executable, executable);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 10;
    }
    status = PyConfig_SetBytesString(&config, &config.program_name, executable);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 10;
    }

    char *argv[2] = {(char *)script, (char *)port_file};
    status = PyConfig_SetBytesArgv(&config, 2, argv);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 12;
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        fprintf(log, "bridge: Py_InitializeFromConfig failed: %s (%s)\n",
                status.func ? status.func : "?", status.err_msg ? status.err_msg : "?");
        fflush(log);
        return 13;
    }

    FILE *source = fopen(script, "r");
    if (source == NULL) {
        fprintf(log, "bridge: cannot open %s\n", script);
        fflush(log);
        return 14;
    }
    // Point sys.stdout/sys.stderr at the log file before running the script,
    // so import-time failures land somewhere readable.
    PyObject *path_obj = PyUnicode_FromString(log_path);
    PyObject *path_repr = path_obj ? PyObject_Repr(path_obj) : NULL;
    const char *quoted = path_repr ? PyUnicode_AsUTF8(path_repr) : NULL;
    if (quoted != NULL) {
        char redirect[4096];
        snprintf(redirect, sizeof redirect,
                 "import sys; _log = open(%s, 'a', 1); sys.stdout = _log; sys.stderr = _log", quoted);
        PyRun_SimpleString(redirect);
    }
    Py_XDECREF(path_repr);
    Py_XDECREF(path_obj);

    PyObject *module = PyImport_AddModule("__main__");
    PyObject *globals = module ? PyModule_GetDict(module) : NULL;
    if (globals != NULL) {
        // PyRun_File does not populate __main__'s namespace, so fill in what a
        // normal script would get: __file__, __name__ and __builtins__.
        PyObject *file_obj = PyUnicode_FromString(script);
        if (file_obj != NULL) {
            PyDict_SetItemString(globals, "__file__", file_obj);
            Py_DECREF(file_obj);
        }
        PyObject *name_obj = PyUnicode_FromString("__main__");
        if (name_obj != NULL) {
            PyDict_SetItemString(globals, "__name__", name_obj);
            Py_DECREF(name_obj);
        }
        PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins());
        PyDict_SetItemString(globals, "__spec__", Py_None);
    }
    PyObject *result = globals ? PyRun_File(source, script, Py_file_input, globals, globals) : NULL;
    fclose(source);
    if (result == NULL) {
        PyErr_Print();
        return 15;
    }
    Py_DECREF(result);

    Py_FinalizeEx();
    return 0;
}
