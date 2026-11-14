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

    fprintf(log, "bridge: interpreter ready\n");
    fflush(log);

    FILE *source = fopen(script, "r");
    if (source == NULL) {
        fprintf(log, "bridge: cannot open %s\n", script);
        fflush(log);
        return 14;
    }
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
    fprintf(log, "bridge: running boot.py\n");
    fflush(log);
    PyObject *result = globals ? PyRun_File(source, script, Py_file_input, globals, globals) : NULL;
    fclose(source);
    if (result == NULL) {
        // Format the exception in C as well: the Python-level stderr may be
        // unusable if the failure happened before it was set up.
        PyObject *etype = NULL, *evalue = NULL, *etb = NULL;
        PyErr_Fetch(&etype, &evalue, &etb);
        PyErr_NormalizeException(&etype, &evalue, &etb);
        PyObject *text = NULL;
        PyObject *tb_module = PyImport_ImportModule("traceback");
        if (tb_module != NULL) {
            PyObject *lines = PyObject_CallMethod(tb_module, "format_exception", "OOO",
                etype ? etype : Py_None, evalue ? evalue : Py_None, etb ? etb : Py_None);
            if (lines != NULL) {
                PyObject *separator = PyUnicode_FromString("");
                text = separator ? PyUnicode_Join(separator, lines) : NULL;
                Py_XDECREF(separator);
                Py_DECREF(lines);
            }
            Py_DECREF(tb_module);
        }
        const char *message = text ? PyUnicode_AsUTF8(text) : NULL;
        fprintf(log, "bridge: boot.py failed\n%s\n", message ? message : "(no traceback)");
        fflush(log);
        Py_XDECREF(text);
        Py_XDECREF(etype);
        Py_XDECREF(evalue);
        Py_XDECREF(etb);
        return 15;
    }
    fprintf(log, "bridge: script returned\n");
    fflush(log);
    Py_DECREF(result);
    Py_FinalizeEx();
    return 0;
}
