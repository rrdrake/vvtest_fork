#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .outpututils import capture_traceback


class UserPluginError( Exception ):
    pass


class UserPluginBridge:

    def __init__(self, plugin_module):
        ""
        self.plugin = plugin_module

        self.validate = None
        if self.plugin and hasattr( self.plugin, 'validate_test' ):
            self.validate = self.plugin.validate_test

        # avoid flooding output if the user plugin has an error (which
        # raises an exception) by only printing the traceback once for
        # each exception string
        self.exc_uniq = set()

    def validateTest(self, tspec):
        """
        Returns non-empty string (an explanation) if user validation failed.
        """
        rtn = None
        if self.validate != None:
            specs = { 'keywords' : tspec.getKeywords() }
            try:
                rtn = self.validate( specs )
            except Exception:
                xs,tb = capture_traceback( sys.exc_info() )
                self._check_print_exc( xs, tb )
                rtn = xs

        return rtn

    def _check_print_exc(self, xs, tb):
        ""
        if xs not in self.exc_uniq:
            sys.stdout.write( '\n' + tb + '\n' )
            self.exc_uniq.add( xs )


def import_module_by_name( modulename ):
    ""
    mod = None

    try:
        code = compile( 'import '+modulename+' as newmodule',
                        '<string>', 'exec' )
        eval( code, globals() )
        mod = newmodule

    except ImportError:
        pass

    except Exception:
        xs,tb = capture_traceback( sys.exc_info() )
        sys.stdout.write( '\n' + tb + '\n' )
        raise UserPluginError( 'failed to import '+modulename+': '+xs )

    return mod
