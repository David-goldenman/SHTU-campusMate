#include "PythonBridge.h"

#include <Python/Python.h>
#include <stdio.h>

int cm_start_python(const char *home, const char *script, const char *port_file) {
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

    char *argv[2] = {(char *)script, (char *)port_file};
    status = PyConfig_SetBytesArgv(&config, 2, argv);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 12;
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        return 13;
    }

    FILE *source = fopen(script, "r");
    if (source == NULL) {
        return 14;
    }
    PyObject *module = PyImport_AddModule("__main__");
    PyObject *globals = module ? PyModule_GetDict(module) : NULL;
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
