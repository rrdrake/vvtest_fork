#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import fnmatch
import glob

from . import TestSpec
from . import TestExec
from . import TestSpecCreator
from . import CommonSpec
from . import testlistio
from . import FilterExpressions
from .TestSpecError import TestSpecError


class TestList:
    """
    Stores a set of TestSpec objects.  Has utilities to read/write to a text
    file and to read from a test XML file.
    """

    def __init__(self, statushandler, filename, runtime_config=None):
        ""
        self.statushandler = statushandler

        if filename:
            self.filename = os.path.normpath( filename )
        else:
            # use case: scanning tests, but never reading or writing
            self.filename = None

        self.results_suffix = None
        self.results_file = None

        self.datestamp = None
        self.finish = None

        self.groups = ParameterizeAnalyzeGroups( self.statushandler )

        self.tspecs = {}  # TestSpec xdir -> TestSpec object
        # self.active = {}  # TestSpec xdir -> TestSpec object

        self.xtlist = {}  # np -> list of TestExec objects
        self.started = {}  # TestSpec xdir -> TestExec object
        self.stopped = {}  # TestSpec xdir -> TestExec object
        
        self.rtconfig = runtime_config

    def setResultsSuffix(self, suffix=None):
        ""
        if suffix:
            self.results_suffix = suffix
        elif not self.results_suffix:
            self.results_suffix = time.strftime( "%Y-%m-%d_%H:%M:%S" )

        return self.results_suffix

    def getResultsSuffix(self):
        ""
        return self.results_suffix

    def stringFileWrite(self, include_results_suffix=False):
        """
        Writes all the tests in this container to the test list file.  If
        'include_results_suffix' is True, the results suffix is written as
        an attribute in the file.
        """
        assert self.filename

        check_make_directory_containing_file( self.filename )

        tlw = testlistio.TestListWriter( self.filename )

        if include_results_suffix:
            assert self.results_suffix
            tlw.start( results_suffix=self.results_suffix )
        else:
            tlw.start()

        for t in self.tspecs.values():
            tlw.append( t )

        tlw.finish()

    def initializeResultsFile(self):
        ""
        self.setResultsSuffix()

        rfile = self.filename + '.' + self.results_suffix
        
        self.results_file = testlistio.TestListWriter( rfile )

        self.results_file.start()

        return rfile

    def addIncludeFile(self, testlist_path):
        """
        Appends the given filename to the test results file.
        """
        assert self.results_suffix, 'suffix must have already been set'
        inclf = testlist_path + '.' + self.results_suffix
        self.results_file.addIncludeFile( inclf )

    def appendTestResult(self, tspec):
        """
        Appends the results file with the name and attributes of the given
        TestSpec object.
        """
        self.results_file.append( tspec )

    def writeFinished(self):
        """
        Appends the results file with a finish marker that contains the
        current date.
        """
        self.results_file.finish()

    def readTestList(self):
        ""
        assert self.filename

        if os.path.exists( self.filename ):

            tlr = testlistio.TestListReader( self.filename )
            tlr.read()

            self.results_suffix = tlr.getAttr( 'results_suffix', None )

            for xdir,tspec in tlr.getTests().items():
                if xdir not in self.tspecs:
                    self.tspecs[ xdir ] = tspec

    def readTestResults(self, resultsfilename=None):
        ""
        if resultsfilename == None:
            self._read_file_list( self.getResultsFilenames() )
        else:
            self._read_file_list( [ resultsfilename ] )

    def getResultsFilenames(self):
        ""
        assert self.filename
        fileL = glob.glob( self.filename+'.*' )
        fileL.sort()
        return fileL

    def _read_file_list(self, files):
        ""
        for fn in files:

            tlr = testlistio.TestListReader( fn )
            tlr.read()

            self.datestamp = tlr.getStartDate()
            self.finish = tlr.getFinishDate()

            for xdir,tspec in tlr.getTests().items():

                t = self.tspecs.get( xdir, None )
                if t != None:
                    self.statushandler.copyResults( t, tspec )

    def ensureInlinedTestResultIncludes(self):
        ""
        fL = self.getResultsFilenames()
        if len(fL) > 0:
            # only the most recent is checked
            testlistio.inline_include_files( fL[-1] )

    def inlineIncludeFiles(self):
        ""
        rfile = self.filename + '.' + self.results_suffix
        testlistio.inline_include_files( rfile )

    def getDateStamp(self, default=None):
        """
        Return the start date from the last test results file read using the
        readTestResults() function.  If a read has not been done, the 'default'
        argument is returned.
        """
        if self.datestamp:
            return self.datestamp
        return default

    def getFinishDate(self, default=None):
        """
        Return the finish date from the last test results file read using the
        readTestResults() function.  If a read has not been done, or vvtest is
        still running, or vvtest got killed in the middle of running, the
        'default' argument is returned.
        """
        if self.finish:
            return self.finish
        return default

    def getTests(self):
        """
        Returns, in a list, all tests either scanned or read from a file.
        """
        return self.tspecs.values()

    def applyPermanentFilters(self):
        ""
        # magic: this smells (when should groups get rebuilt??)
        self.groups.rebuild( self.tspecs )

        apply_permanent_filters( self.statushandler, self.tspecs,
                                 self.groups, self.rtconfig )

        # magic: this smells (would be fixed by marking the tests)
        # self.active.clear()
        # self.active.update( self.tspecs )
        self.numactive = count_active( self.statushandler, self.tspecs )

    def determineActiveTests(self, filter_dir=None,
                                   analyze_only=False,
                                   baseline=False):
        ""
        # self.active.clear()

        subdir = None
        if filter_dir != None:
            subdir = os.path.normpath( filter_dir )
            if subdir == '' or subdir == '.':
                subdir = None

        apply_runtime_filters( self.statushandler, self.tspecs,
                                             self.rtconfig, subdir,
                                             analyze_only, baseline )

        self.groups.rebuild( self.tspecs )
        self.numactive = count_active( self.statushandler, self.tspecs )

    def markTestsWithDependents(self):
        ""
        for tx in self.getTestExecList():
            if tx.hasDependent():
                tx.atest.setAttr( 'hasdependent', True )

    def getActiveTests(self, sorting=''):
        """
        Get a list of the active tests (after filtering).  If 'sorting' is
        not an empty string, it should be a set of characters that control the
        way the test sorting is performed.
                n : test name (the default)
                x : execution directory name
                t : test run time
                d : execution date
                s : test status (such as pass, fail, diff, etc)
                r : reverse the order
        """
        tL = []
        if not sorting:
            for tspec in self.tspecs.values():
                if not self.statushandler.skipTest( tspec ):
                    tL.append( tspec )
            tL.sort()

        else:
            for t in self.tspecs.values():
                if not self.statushandler.skipTest(t):
                    subL = []
                    for c in sorting:
                        if c == 'n':
                            subL.append( t.getName() )
                        elif c == 'x':
                            subL.append( t.getExecuteDirectory() )
                        elif c == 't':
                            tm = self.statushandler.getRuntime( t, None )
                            if tm == None: tm = 0
                            subL.append( tm )
                        elif c == 'd':
                            subL.append( self.statushandler.getStartDate( t, 0 ) )
                        elif c == 's':
                            subL.append( self.statushandler.getResultStatus( t ) )

                    subL.append( t )
                    tL.append( subL )
            tL.sort()
            if 'r' in sorting:
                tL.reverse()
            tL = [ L[-1] for L in tL ]

        return tL

    def scanDirectory(self, base_directory, force_params=None):
        """
        Recursively scans for test XML or VVT files starting at 'base_directory'.
        If 'force_params' is not None, it must be a dictionary mapping
        parameter names to a list of parameter values.  Any test that contains
        a parameter in this dictionary will take on the given values for that
        parameter.
        """
        bdir = os.path.normpath( os.path.abspath(base_directory) )
        for root,dirs,files in os.walk( bdir ):
            self._scan_recurse( bdir, force_params, root, dirs, files )

    def _scan_recurse(self, basedir, force_params, d, dirs, files):
        """
        This function is given to os.walk to recursively scan a directory
        tree for test XML files.  The 'basedir' is the directory originally
        sent to the os.walk function.
        """
        d = os.path.normpath(d)

        if basedir == d:
            reldir = '.'
        else:
            assert basedir+os.sep == d[:len(basedir)+1]
            reldir = d[len(basedir)+1:]

        # scan files with extension "xml" or "vvt"; soft links to directories
        # are skipped by os.walk so special handling is performed

        for f in files:
            bn,ext = os.path.splitext(f)
            df = os.path.join(d,f)
            if bn and ext in ['.xml','.vvt']:
                self.readTestFile( basedir, os.path.join(reldir,f), force_params )

        linkdirs = []
        for subd in list(dirs):
            rd = os.path.join( d, subd )
            if not os.path.exists(rd) or \
                    subd.startswith("TestResults.") or \
                    subd.startswith("Build_"):
                dirs.remove( subd )
            elif os.path.islink(rd):
                linkdirs.append( rd )

        # TODO: should check that the soft linked directories do not
        #       point to a parent directory of any of the directories
        #       visited thus far (to avoid an infinite scan loop)
        #       - would have to use os.path.realpath() or something because
        #         the actual path may be the softlinked path rather than the
        #         path obtained by following '..' all the way to root

        # manually recurse into soft linked directories
        for ld in linkdirs:
            for lroot,ldirs,lfiles in os.walk( ld ):
                self._scan_recurse( basedir, force_params, lroot, ldirs, lfiles )
    
    def readTestFile(self, basepath, relfile, force_params):
        """
        Initiates the parsing of a test file.  XML test descriptions may be
        skipped if they don't appear to be a test file.  Attributes from
        existing tests will be absorbed.
        """
        assert basepath
        assert relfile
        assert os.path.isabs( basepath )
        assert not os.path.isabs( relfile )

        basepath = os.path.normpath( basepath )
        relfile  = os.path.normpath( relfile )

        assert relfile

        try:
          testL = createTestObjects(
                        basepath, relfile, force_params, self.rtconfig )
        except TestSpecError:
          print3( "*** skipping file " + os.path.join( basepath, relfile ) + \
                  ": " + str( sys.exc_info()[1] ) )
          testL = []

        for t in testL:
            # this new test is ignored if it was already read from source
            # (or a different test source but the same relative path from root)
            xdir = t.getExecuteDirectory()

            # magic: this is where a warning about the same xdir would be generated
            if xdir not in self.tspecs:
                self.tspecs[xdir] = t

    def addTest(self, t):
        """
        Add a test to the test spec list.  Will overwrite an existing test.
        """
        self.tspecs[ t.getExecuteDirectory() ] = t
    
    def createTestExecs(self, test_dir, platform, config, perms):
        """
        Creates the set of TestExec objects from the active test list.
        """
        d = os.path.join( config.get('toolsdir'), 'libvvtest' )
        c = config.get('configdir')
        xdb = CommonSpec.loadCommonSpec( d, c )

        self._createTestExecList( perms )
        
        for xt in self.getTestExecList():
            xt.init( test_dir, platform, xdb, config )
    
    def _createTestExecList(self, perms):
        """
        """
        self.xtlist = {}

        xtD = {}
        for t in self.tspecs.values():

            if not self.statushandler.skipTest( t ):

                assert t.constructionCompleted()

                xt = TestExec.TestExec( self.statushandler, t, perms )

                if t.getAttr( 'hasdependent', False ):
                    xt.setHasDependent()

                np = int( t.getParameters().get('np', 0) )
                if np in self.xtlist:
                    self.xtlist[np].append(xt)
                else:
                    self.xtlist[np] = [xt]

                xtD[ t.getExecuteDirectory() ] = xt

        # sort tests longest running first; 
        self.sortTestExecList()

        self._add_analyze_dependencies( xtD )
        self._add_general_dependencies( xtD )

    def _add_analyze_dependencies(self, xdir2testexec):
        """
        add dependencies of analyze tests to TestExec objects
        """
        for xt in self.getTestExecList():
            analyze_xdir = self.groups.getAnalyzeExecuteDirectory( xt.atest )
            if analyze_xdir != None:
                # this test has an analyze dependent
                analyze_xt = xdir2testexec.get( analyze_xdir, None )
                if analyze_xt != None:
                    connect_dependency( analyze_xt, xt )
            elif xt.atest.isAnalyze():
                grpL = self.groups.getGroup( xt.atest )
                for gt in grpL:
                    if not gt.isAnalyze():
                        connect_dependency( xt, gt )

    def _add_general_dependencies(self, xdir2testexec):
        """
        add general dependencies to TestExec objects
        """
        xdirlist = self.tspecs.keys()
        for xt in self.getTestExecList():
            xdir = xt.atest.getExecuteDirectory()
            for dep_pat,expr in xt.atest.getDependencies():
                depL = find_tests_by_execute_directory_match(
                                                xdir, dep_pat, xdirlist )
                for dep_xdir in depL:
                    dep_obj = xdir2testexec.get(
                                    dep_xdir,
                                    self.tspecs.get( dep_xdir, None ) )
                    if dep_obj != None:
                        connect_dependency( xt, dep_obj, dep_pat, expr )

    def sortTestExecList(self):
        """
        Sort the TestExec objects by runtime, descending order.  This is so
        popNext() will try to avoid launching long running tests at the end
        of the testing sequence, which can add significantly to the total wall
        time.
        """
        for np,L in self.xtlist.items():
            sortL = []
            for tx in L:
                t = tx.atest
                tm = self.statushandler.getRuntime( t, None )
                if tm == None: tm = 0
                sortL.append( (tm,tx) )
            sortL.sort()
            sortL.reverse()
            L[:] = [ tx for tm,tx in sortL ]

    def getTestExecProcList(self):
        """
        Returns a list of integers; each integer is the number of processors
        needed by one or more tests in the TestExec list.
        """
        return self.xtlist.keys()
    
    def getTestExecList(self, numprocs=None):
        """
        If 'numprocs' is None, all TestExec objects are returned.  If 'numprocs'
        is not None, a list of TestExec objects is returned each of which need
        that number of processors to run.
        """
        L = []
        if numprocs == None:
          for txL in self.xtlist.values():
            L.extend( txL )
        else:
          L.extend( self.xtlist.get(numprocs,[]) )
        return L
    
    def popNext(self, platform):
        """
        Finds a test to execute.  Returns a TestExec object, or None if no
        test can run.  In this case, one of the following is true
        
            1. there are not enough free processors to run another test
            2. the only tests left are parent tests that cannot be run
               because one or more of their children did not pass or diff

        In the latter case, numRunning() will be zero.
        """
        npL = list( self.xtlist.keys() )
        npL.sort()
        npL.reverse()

        # find longest runtime test such that the num procs is available
        tx = self._pop_next_test( npL, platform )
        if tx == None and len(self.started) == 0:
            # search for tests that need more processors than platform has
            tx = self._pop_next_test( npL )

        if tx != None:
            self.started[ tx.atest.getExecuteDirectory() ] = tx

        return tx

    def popRemaining(self):
        """
        All remaining tests are removed from the run list and returned.
        """
        tL = []
        for np,L in list( self.xtlist.items() ):
            tL.extend( L )
            del L[:]
            self.xtlist.pop( np )
        return tL

    def getRunning(self):
        """
        Return the list of tests that are still running.
        """
        return self.started.values()

    def testDone(self, tx):
        """
        """
        xdir = tx.atest.getExecuteDirectory()
        self.appendTestResult( tx.atest )
        self.started.pop( xdir )
        self.stopped[ xdir ] = tx

    def numActive(self):
        """
        Return the total number of active tests (the tests that are to be run).
        """
        return self.numactive

    def numDone(self):
        """
        Return the number of tests that have been run.
        """
        return len(self.stopped)

    def numRunning(self):
        """
        Return the number of tests are currently running.
        """
        return len(self.started)

    def _pop_next_test(self, npL, platform=None):
        """
        """
        for np in npL:
            if platform == None or platform.queryProcs(np):
                tL = self.xtlist[np]
                N = len(tL)
                i = 0
                while i < N:
                    tx = tL[i]
                    if tx.getBlockingDependency() == None:
                        self._pop_test_exec( np, i )
                        return tx
                    i += 1
        return None

    def _pop_test_exec(self, np, i):
        """
        """
        L = self.xtlist[np]
        del L[i]
        if len(L) == 0:
            self.xtlist.pop( np )


def filter_by_cummulative_runtime( statushandler, activedict, rtsum ):
    ""
    rmD = {}

    # first, generate list with times
    tL = []
    for xdir,t in activedict.items():
        tm = statushandler.getRuntime( t, None )
        if tm == None: tm = 0
        tL.append( (tm,xdir,t) )
    tL.sort()

    # accumulate tests until allowed runtime is exceeded
    tsum = 0.
    i = 0 ; n = len(tL)
    while i < n:
        tm,xdir,t = tL[i]
        if not statushandler.skipTest( t ):
            tsum += tm
            if tsum > rtsum:
                statushandler.markSkip( t, 'cummulative runtime threshhold' )

                # analyze_xdir = groups.getAnalyzeExecuteDirectory( t )
                # if analyze_xdir:
                #     analyze_tspec = activedict.get( analyze_xdir, None )
                #     if analyze_tspec:
                #         if not statushandler.skipTest( analyze_tspec ):
                #             statushandler.markSkip( analyze_tspec,
                #                     'filtered out due to child' )

        i += 1

    # put the rest of the tests in the remove dict
    # while i < n:
    #     tm,xdir,t = tL[i]
    #     rmD[xdir] = t
    #     i += 1
    # tL = None

    # return rmD


def is_subdir(parent_dir, subdir):
    """
    TODO: test for relative paths
    """
    lp = len(parent_dir)
    ls = len(subdir)
    if ls > lp and parent_dir + '/' == subdir[0:lp+1]:
      return subdir[lp+1:]
    return None


def check_make_directory_containing_file( filename ):
    ""
    d,b = os.path.split( filename )
    if d and d != '.':
        if not os.path.exists(d):
            os.mkdir( d )


class ParameterizeAnalyzeGroups:

    def __init__(self, statushandler):
        ""
        self.statushandler = statushandler
        self.groupmap = {}  # (test filepath, test name) -> list of TestSpec

    def getGroup(self, tspec):
        ""
        key = ( tspec.getFilepath(), tspec.getName() )
        return self.groupmap[key]

    def getAnalyzeGroup(self, tspec, *default):
        ""
        grpL = self.getGroup( tspec )

        for t in grpL:
            if t.isAnalyze():
                return grpL

        return default[0]

    def getAnalyzeExecuteDirectory(self, tspec):
        ""
        grpL = self.getGroup( tspec )

        for t in grpL:
            if t != tspec and t.isAnalyze():
                return t.getExecuteDirectory()

        return None

    def rebuild(self, tspecs):
        ""
        self.groupmap.clear()

        for xdir,t in tspecs.items():

            if not self.statushandler.skipTestByParameter(t):

                # this key is common to each test in a parameterize/analyze
                # test group (including the analyze test)
                key = ( t.getFilepath(), t.getName() )

                L = self.groupmap.get( key, None )
                if L == None:
                    L = []
                    self.groupmap[ key ] = L

                L.append( t )


def find_tests_by_execute_directory_match( xdir, pattern, xdir_list ):
    """
    Given 'xdir' dependent execute directory, the shell glob 'pattern' is
    matched against the execute directories in the 'xdir_list', in this order:

        1. basename(xdir)/pat
        2. basename(xdir)/*/pat
        3. pat
        4. *pat

    The first of these that matches at least one test will be returned.

    A python set of xdir is returned.
    """
    tbase = os.path.dirname( xdir )
    if tbase == '.':
        tbase = ''
    elif tbase:
        tbase += '/'

    L1 = [] ; L2 = [] ; L3 = [] ; L4 = []

    for xdir in xdir_list:

        p1 = os.path.normpath( tbase+pattern )
        if fnmatch.fnmatch( xdir, p1 ):
            L1.append( xdir )

        if fnmatch.fnmatch( xdir, tbase+'*/'+pattern ):
            L2.append( xdir )

        if fnmatch.fnmatch( xdir, pattern ):
            L3.append( xdir )

        if fnmatch.fnmatch( xdir, '*'+pattern ):
            L4.append( xdir )

    for L in [ L1, L2, L3, L4 ]:
        if len(L) > 0:
            return set(L)

    return set()


def connect_dependency( from_test, to_test, pattrn=None, expr=None ):
    ""
    assert isinstance( from_test, TestExec.TestExec )

    from_test.addDependency( to_test, pattrn, expr )

    if isinstance( to_test, TestExec.TestExec ):
        to_test.setHasDependent()


def createTestObjects( rootpath, relpath, force_params, rtconfig ):
    """
    The 'rootpath' is the top directory of the file scan.  The 'relpath' is
    the name of the test file relative to 'rootpath' (it must not be an
    absolute path).  If 'force_params' is not None, then any parameters in
    the test that are in the 'force_params' dictionary have their values
    replaced for that parameter name.
    
    Returns a list of TestSpec objects, including a "parent" test if needed.


    Is the following note about parameter filtering still relevant?  Is it
    any different when filtering is performed above create/refresh?

        Important: this function always applies filtering, even if the
        "include_all" flag is present in 'rtconfig'.  This means any command
        line parameter expressions must be passed along in batch queue mode.

    """
    evaluator = TestSpecCreator.ExpressionEvaluator( rtconfig.platformName(),
                                                     rtconfig.getOptionList() )

    tests = TestSpecCreator.create_unfiltered_testlist( rootpath, relpath,
                                        force_params, evaluator )

    return tests


def apply_permanent_filters( statushandler, tspec_map, groups, rtconfig ):
    ""
    filt = TestFilter( rtconfig, statushandler )

    # magic: "assert include_all" because batch should always be a restart
    include_all = rtconfig.getAttr( 'include_all', False )

    for xdir,tspec in tspec_map.items():

#magic        statushandler.resetSkip( tspec )

        if not include_all:

            if not filt.checkParameters( tspec ):
                statushandler.markSkipByParameter( tspec )

            elif not ( filt.checkPlatform( tspec ) and \
                       filt.checkOptions( tspec ) and \
                       filt.checkKeywords( tspec, results_keywords=False ) and \
                       filt.checkTDD( tspec ) and \
                       filt.checkFileSearch( tspec ) and \
                       filt.checkMaxProcessors( tspec ) and \
                       filt.checkRuntime( tspec ) ):
                statushandler.markSkip( tspec, 'filtered out' )

    rtsum = rtconfig.getAttr( 'runtime_sum', None )
    if not include_all and rtsum != None:
        filter_by_cummulative_runtime( statushandler, tspec_map, rtsum )

    # magic: TODO:
    #   - move this rebuild to top of this function
    #   - add access methods to the "groups" class that consider the skip
    #     status of their children
    #   - use case that will fail otherwise is:
    #       - a bunch of analyze tests that take a considerable amount of time
    #       - they are not excluded before the --tsum filter process
    #       - they are excluded afterwards if all children are excluded by
    #         parameter
    #       - now the tests left to run will take significantly less time
    #         than the --tmax value

    groups.rebuild( tspec_map )

    filter_analyze_tests( statushandler, groups )

def filter_analyze_tests( statushandler, groups ):
    ""
    for key,tspecL in groups.groupmap.items():
        analyze = None
        skip_analyze = False
        paramsets = []
        for tspec in tspecL:
            if tspec.isAnalyze():
                analyze = tspec
            elif statushandler.skipTestCausingAnalyzeSkip( tspec ):
                skip_analyze = True
            else:
                paramsets.append( tspec.getParameters() )

        if analyze != None:
            if skip_analyze:
                statushandler.markSkip( analyze, 'analyze dependency skipped' )
            else:
                def evalfunc( paramD ):
                    for D in paramsets:
                        if paramD == D:
                            return True
                    return False
                pset = analyze.getParameterSet()
                pset.applyParamFilter( evalfunc )


    # for xdir,tspec in tspec_map.items():

    #     if tspec.isAnalyze():
    #         # align the analyze parameter set with its parameterized tests
    #         paramset = tspec.getParameterSet()
    #         paramset.applyParamFilter( rtconfig.evaluate_parameters )

    #     if include_all:
    #         pass

    #     elif not filt.checkParameters( tspec ):
    #         statushandler.markSkip( tspec, 'parameter expression' )

    #     else:
    #         keep = ( filt.checkPlatform( tspec ) and \
    #                  filt.checkOptions( tspec ) and \
    #                  filt.checkKeywords( tspec, results_keywords=False ) and \
    #                  filt.checkTDD( tspec ) and \
    #                  filt.checkFileSearch( tspec ) and \
    #                  filt.checkMaxProcessors( tspec ) and \
    #                  filt.checkRuntime( tspec ) )

    #         if not keep:
    #             statushandler.markSkip( tspec, 'filtered out' )

    #             analyze_xdir = groups.getAnalyzeExecuteDirectory( tspec )
    #             if analyze_xdir:
    #                 analyze_tspec = tspec_map.get( analyze_xdir, None )
    #                 if analyze_tspec:
    #                     if not statushandler.skipTest( analyze_tspec ):
    #                         statushandler.markSkip( analyze_tspec,
    #                                 'filtered out due to child' )

    # rtsum = rtconfig.getAttr( 'runtime_sum', None )
    # if not include_all and rtsum != None:
    #     apply_cummulative_runtime_filter( statushandler, tspec_map, rtsum, groups )


def apply_runtime_filters( statushandler, tspec_map, rtconfig, subdir,
                           analyze_only, baseline ):
    ""
    filt = TestFilter( rtconfig, statushandler )

    include_all = rtconfig.getAttr( 'include_all', False )

    for xdir,tspec in tspec_map.items():

        if not statushandler.skipTest( tspec ):

            keep = True

            if not include_all:

                if subdir and subdir != xdir and not is_subdir( subdir, xdir ):
                    keep = False
                    statushandler.markSkip( tspec, 'subdir' )

                if keep and not \
                        filt.checkKeywords( tspec, results_keywords=True ):
                    keep = False
                    statushandler.markSkip( tspec, 'results keyword expression' )

                if keep and not filt.checkParameters( tspec ):
                    keep = False
                    statushandler.markSkip( tspec, 'restart parameter expression failed' )

                if keep:
                    keep = ( filt.checkPlatform( tspec ) and \
                             filt.checkOptions( tspec ) and \
                             filt.checkTDD( tspec ) and \
                             filt.checkFileSearch( tspec ) and \
                             filt.checkMaxProcessors( tspec ) and \
                             filt.checkRuntime( tspec ) )
                    if not keep:
                        statushandler.markSkip( tspec, 'filter' )

            if keep and not tspec.constructionCompleted():
                # magic: this smells (use the 'status' field??)
                # plus, how to avoid refresh just for vvtest -i ??
                refreshTest( tspec, rtconfig )

            if keep:
                # magic: an ugly thing here is the baseline script is only loaded
                #        after a refresh, so this test has to be after
                if baseline and not tspec.hasBaseline():
                    statushandler.markSkip( tspec, 'no baseline handling' )

    rtsum = rtconfig.getAttr( 'runtime_sum', None )
    if not include_all and rtsum != None:
        filter_by_cummulative_runtime( statushandler, tspec_map, rtsum )

    # magic: turning this on causes failures because results_keywords=True
    #        causes analyze tests to be skipped (params, analyze_filtering)
    if not baseline:
        groups = ParameterizeAnalyzeGroups( statushandler )
        groups.rebuild( tspec_map )
        filter_analyze_tests( statushandler, groups )

# def apply_cummulative_runtime_filter( statushandler, active, rtsum, groups=None ):
#     ""
#     if groups == None:
#         groups = ParameterizeAnalyzeGroups( statushandler )
#         groups.rebuild( active )

#     filter_by_cummulative_runtime( statushandler, active, rtsum, groups )


def count_active( statushandler, tspec_map ):
    ""
    cnt = 0
    for tspec in tspec_map.values():
        if not statushandler.skipTest( tspec ):
            cnt += 1
    return cnt


def refreshTest( testobj, rtconfig ):
    """
    Parses the test source file and resets the settings for the given test.
    The test name is not changed.  The parameters in the test XML file are
    not considered; instead, the parameters already defined in the test
    object are used.

    If the test XML contains bad syntax, a TestSpecError is raised.
    
    Returns false if any of the filtering would exclude this test.
    """
    evaluator = TestSpecCreator.ExpressionEvaluator( rtconfig.platformName(),
                                                     rtconfig.getOptionList() )

    TestSpecCreator.reparse_test_object( testobj, evaluator )

    if testobj.isAnalyze():
        # if analyze test, filter the parameter set to the parameters
        # that would be included
        paramset = testobj.getParameterSet()
        paramset.applyParamFilter( rtconfig.evaluate_parameters )


class TestFilter:

    def __init__(self, rtconfig, statushandler):
        ""
        self.rtconfig = rtconfig
        self.statushandler = statushandler

    def checkPlatform(self, tspec):
        ""
        pev = PlatformEvaluator( tspec.getPlatformEnableExpressions() )
        ok = self.rtconfig.evaluate_platform_include( pev.satisfies_platform )
        return ok

    def checkOptions(self, tspec):
        ""
        for opexpr in tspec.getOptionEnableExpressions():
            if not self.rtconfig.evaluate_option_expr( opexpr ):
                return False
        return True

    def checkKeywords(self, tspec, results_keywords=True):
        ""
        kwlist = tspec.getKeywords() + \
                 self.statushandler.getResultsKeywords( tspec )
        ok = self.rtconfig.satisfies_keywords( kwlist, results_keywords )
        return ok

    def checkTDD(self, tspec):
        ""
        if self.rtconfig.getAttr( 'include_tdd', False ):
            ok = True
        else:
            ok = ( 'TDD' not in tspec.getKeywords() )
        return ok

    def checkParameters(self, tspec):
        ""
        if tspec.isAnalyze():
            # analyze tests are not excluded by parameter expressions
            ok = True
        else:
            ok = self.rtconfig.evaluate_parameters( tspec.getParameters() )
        return ok

    def checkFileSearch(self, tspec):
        ""
        ok = self.rtconfig.file_search( tspec )
        return ok

    def checkMaxProcessors(self, tspec):
        ""
        np = int( tspec.getParameters().get( 'np', 1 ) )
        ok = self.rtconfig.evaluate_maxprocs( np )
        return ok

    def checkRuntime(self, tspec):
        ""
        tm = self.statushandler.getRuntime( tspec, None )
        if tm != None and not self.rtconfig.evaluate_runtime( tm ):
            return False
        return True


class PlatformEvaluator:
    """
    Tests can use platform expressions to enable/disable the test.  This class
    caches the expressions and provides a function that answers the question

        "Would the test run on the given platform name?"
    """
    def __init__(self, list_of_word_expr):
        self.exprL = list_of_word_expr

    def satisfies_platform(self, plat_name):
        ""
        for wx in self.exprL:
            if not wx.evaluate( lambda tok: tok == plat_name ):
                return False
        return True


###########################################################################


def print3( *args ):
    sys.stdout.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
    sys.stdout.flush()
