#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import platform

from . import rpool
from . import rprobe


class Platform:

    def __init__(self, vvtesthome, optdict):
        ""
        self.vvtesthome = vvtesthome
        self.optdict = optdict

        self.plugin_maxprocs = None
        self.procpool = rpool.ResourcePool( 1, 1 )
        self.devicepool = None

        self.platname = None
        self.cplrname = None

        self.envD = {}
        self.attrs = {}

        self.batchspec = None

    # ----------------------------------------------------------------

    def getName(self):  return self.platname
    def getCompiler(self): return self.cplrname
    def getOptions(self): return self.optdict

    def getMaxSize(self):
        ""
        maxnp = self.procpool.maxAvailable()
        if self.devicepool != None:
            maxnd = self.devicepool.maxAvailable()
        else:
            maxnd = 0
        return (maxnp,maxnd)

    def getComputeNodeSize(self):
        ""
        pass  # magic

    def getSize(self):
        ""
        np = self.procpool.numTotal()
        if self.devicepool != None:
            nd = self.devicepool.numTotal()
        else:
            nd = 0
        return (np,nd)

    def getPluginMaxProcs(self):
        ""
        return self.plugin_maxprocs

    def display(self, isbatched=False):
        ""
        s = "Platform " + self.platname
        if not isbatched:
            np,nd = self.getSize()
            maxnp,maxnd = self.getMaxSize()
            s += ", num procs = " + str(np)
            s += ", max procs = " + str(maxnp)
            if self.devicepool != None:
                s += ', num devices = '+str(nd)
                s += ', max devices = '+str(maxnd)
        print ( s )

    def getEnvironment(self):
        """
        Returns a dictionary of environment variables and their values.
        """
        return self.envD

    # ----------------------------------------------------------------

    def setenv(self, name, value):
        """
        """
        if value == None:
            if name in self.envD:
                del self.envD[name]
        else:
            self.envD[name] = value

    def setattr(self, name, value):
        """
        """
        if value == None:
            if name in self.attrs:
                del self.attrs[name]
        else:
            self.attrs[name] = value

    def getattr(self, name, *default):
        ""
        if len(default) > 0:
            return self.attrs.get( name, default[0] )
        else:
            return self.attrs[name]

    def setBatchSystem(self, batch, ppn, **kwargs ):
        ""
        assert ppn and ppn > 0

        self.batchspec = ( batch, ppn, kwargs )

    def initializeBatchSystem(self, batchitf):
        ""
        if self.batchspec:
            qtype,ppn,kwargs = self.batchspec
            batchitf.setQueueType( qtype, ppn, **kwargs )

        for n,v in self.envD.items():
            batchitf.setEnviron( n, v )

        for n,v in self.attrs.items():
            batchitf.setAttr( n, v )

    def getDefaultQsubLimit(self):
        ""
        n = self.attrs.get( 'maxsubs', 5 )
        return n

    def initProcs(self, num_procs, max_procs, num_devices, max_devices ):
        """
        Determine and set the number of CPU cores and devices.  The arguments
        are from the command line:

            num_procs   is -n
            num_devices is --devices
            max_procs   is -N
            max_devices is --max-devices
        """
        self.plugin_maxprocs = self.attrs.get( 'maxprocs', None )

        np,maxnp = \
            determine_processor_cores( num_procs,
                                       max_procs,
                                       self.plugin_maxprocs )

        nd,maxdev = \
            determine_device_count( num_devices,
                                    max_devices,
                                    self.attrs.get( 'maxdevices', None ) )

        self.procpool = rpool.ResourcePool( np, maxnp )

        if nd != None:
            assert maxdev != None
            self.devicepool = rpool.ResourcePool( nd, maxdev )

    def sizeAvailable(self):
        ""
        sznp = self.procpool.numAvailable()
        if self.devicepool == None:
            return ( sznp, 0 )
        else:
            return ( sznp, self.devicepool.numAvailable() )

    def getResources(self, size):
        ""
        np,ndevice = size

        procs = self.procpool.get( np )

        if self.devicepool == None or ndevice == None:
            devices = None
        else:
            devices = self.devicepool.get( max( 0, int(ndevice) ) )

        job_info = construct_job_info( procs, self.procpool,
                                       devices, self.devicepool,
                                       self.getattr( 'mpifile', '' ),
                                       self.getattr( 'mpiopts', '' ) )

        return job_info

    def returnResources(self, job_info):
        ""
        self.procpool.put( job_info.procs )
        if self.devicepool != None and job_info.devices != None:
            self.devicepool.put( job_info.devices )

    # ----------------------------------------------------------------

    def testingDirectory(self):
        """
        """
        if 'TESTING_DIRECTORY' in os.environ:
            return os.environ['TESTING_DIRECTORY']

        elif 'testingdir' in self.attrs:
            return self.attrs['testingdir']

        return None

    def which(self, prog):
        """
        """
        if not prog:
          return None
        if os.path.isabs(prog):
          return prog
        for d in os.environ['PATH'].split(':'):
          if not d: d = '.'
          if os.path.isdir(d):
            f = os.path.join( d, prog )
            if os.path.exists(f) and \
               os.access(f,os.R_OK) and os.access(f,os.X_OK):
              if not os.path.isabs(f):
                f = os.path.abspath(f)
              return os.path.normpath(f)
        return None


def determine_processor_cores( num_procs, max_procs, plugin_max ):
    ""
    if max_procs == None:
        if plugin_max == None:
            mx = rprobe.probe_num_processors( 4 )
        else:
            mx = plugin_max
    else:
        mx = max_procs

    if num_procs == None:
        np = mx
    else:
        np = num_procs

    return np,mx


def determine_device_count( num_devices, max_devices, plugin_max ):
    ""
    if max_devices == None:
        mx = plugin_max
    else:
        mx = max_devices

    if num_devices == None:
        nd = mx
    else:
        nd = num_devices
        if mx == None:
            # could probe for devices to get a better max
            mx = num_devices

    return nd,mx


def create_Platform_instance( vvtestdir, platname, isbatched, platopts,
                              numprocs, maxprocs, devices, max_devices,
                              onopts, offopts ):
    ""
    assert vvtestdir
    assert os.path.exists( vvtestdir )
    assert os.path.isdir( vvtestdir )

    optdict = {}
    if platname:         optdict['--plat']    = platname
    if platopts:         optdict['--platopt'] = platopts
    if onopts:           optdict['-o']        = onopts
    if offopts:          optdict['-O']        = offopts

    plat = Platform( vvtestdir, optdict )

    platname,cplrname = get_platform_and_compiler(
                                platname,
                                None,  # compiler name not used anymore
                                onopts,
                                offopts )

    plat.platname = platname
    plat.cplrname = cplrname

    set_platform_options( plat, platopts )

    if isbatched:
        # this may get overridden by platform_plugin.py
        plat.setBatchSystem( 'procbatch', 1 )

    initialize_platform( plat )

    plat.initProcs( numprocs,
                    maxprocs,
                    devices,
                    max_devices )

    return plat


def set_platform_options( plat, platopts ):
    ""
    q = platopts.get( 'queue', platopts.get( 'q', None ) )
    plat.setattr( 'queue', q )

    act = platopts.get( 'account', platopts.get( 'PT', None ) )
    plat.setattr( 'account', act )

    wall = platopts.get( 'walltime', None )
    plat.setattr( 'walltime', wall )

    # QoS = "Quality of Service" e.g. "normal", "long", etc.
    QoS = platopts.get( 'QoS', None )
    plat.setattr( 'QoS', QoS )


def get_platform_and_compiler( platname, cplrname, onopts, offopts ):
    ""
    idplatform = import_idplatform()

    optdict = convert_to_option_dictionary( platname, cplrname, onopts, offopts )

    if not platname:
        if idplatform != None and hasattr( idplatform, "platform" ):
            platname = idplatform.platform( optdict )
        if not platname:
            platname = platform.uname()[0]

    if not cplrname:
        if idplatform != None and hasattr( idplatform, "compiler" ):
            cplrname = idplatform.compiler( platname, optdict )

    return platname, cplrname


def initialize_platform( plat ):
    ""
    plug = import_platform_plugin()

    if plug != None and hasattr( plug, 'initialize' ):
        plug.initialize( plat )


def import_idplatform():
    ""
    try:
        # this comes from the config directory
        import idplatform
    except ImportError:
        idplatform = None

    return idplatform


def import_platform_plugin():
    ""
    try:
        # this comes from the config directory
        import platform_plugin
    except ImportError:
        platform_plugin = None

    return platform_plugin


def convert_to_option_dictionary( platname, cplrname, onopts, offopts ):
    ""
    optdict = {}

    if platname: optdict['--plat'] = platname
    if cplrname: optdict['--cplr'] = cplrname

    optdict['-o'] = onopts
    optdict['-O'] = offopts

    return optdict


##########################################################################

class JobInfo:
    """
    This object is used to communicate and hold information for a job
    processor request, including a string to give to the mpirun command, if
    any.  It is returned to the Platform when the job finishes.
    """
    def __init__(self, procs, maxprocs):
        ""
        self.procs = procs
        self.maxprocs = maxprocs
        self.devices = None
        self.maxdevices = None
        self.mpi_opts = ''


def construct_job_info( procs, procpool,
                        devices, devicepool,
                        mpifile, mpiopts ):
    ""
    numprocs = procpool.numTotal()
    maxprocs = procpool.maxAvailable()

    job_info = JobInfo( procs, maxprocs )

    if devices != None:
        job_info.devices = devices
        job_info.maxdevices = devicepool.maxAvailable()

    if mpifile == 'hostfile':
        # use OpenMPI style machine file
        job_info.mpi_opts = "--hostfile machinefile"
        slots = min( len(procs), numprocs )
        job_info.machinefile = \
                    platform.uname()[1].strip() + " slots=" + str(slots) + '\n'

    elif mpifile == 'machinefile':
        # use MPICH style machine file
        job_info.mpi_opts = "-machinefile machinefile"
        job_info.machinefile = ''
        for i in range(len(procs)):
            job_info.machinefile += machine + '\n'

    if mpiopts:
        job_info.mpi_opts += ' ' + mpiopts

    return job_info
