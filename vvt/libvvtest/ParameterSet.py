#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os


class ParameterSet:
    """
    A set of parameter names mapped to their values.  Such as

        paramA = [ 'Aval1', 'Aval2', ... ]
        paramB = [ 'Bval1', 'Bval2', ... ]
        ...

    A set of instances is the cartesian product of the values (an instance
    is a dictionary of param_name=param_value).  Such as

        { 'paramA':'Aval1', 'paramB':'Bval1', ... }
        { 'paramA':'Aval1', 'paramB':'Bval2', ... }
        { 'paramA':'Aval2', 'paramB':'Bval1', ... }
        { 'paramA':'Aval2', 'paramB':'Bval2', ... }
        ...

    Parameter names can be grouped, such as

        paramC,paramD = [ ('Cval1','Dval1'), ('Cval2','Dval2'), ... ]

    The cartesian product does NOT apply to values within a group (the values
    are taken verbatim).
    """

    def __init__(self):
        ""
        self.params = []
        self.instances = []

    def addParameter(self, name, value_list):
        """
        Such as 'myparam', ['value1', 'value2'].
        """
        names = [ name ]
        values_list = [ [val] for val in value_list ]
        self.addParameterGroup( names, values_list )

    def addParameterGroup(self, names, values_list):
        """
        Such as ['paramA','paramB'], [ ['A1','B1'], ['A2','B2'] ].
        """
        if len(self.params) == 0:
            curL = [ {} ]  # a seed for the accumulation algorithm
        else:
            curL = self.instances

        self.instances = \
            accumulate_parameter_group_list( curL, names, values_list )

        self.params.append( ( [] + names, [] + values_list) )

    def applyParamFilter(self, param_filter):
        """
        The param_filter.evaluate() method is used to filter down the set of
        parameter instances.  The list returned with getInstances() will
        reflect the filtering.
        """
        self._reconstructInstances()

        newL = []
        for instD in self.instances:
            if param_filter.evaluate( instD ):
                newL.append( instD )

        self.instances = newL

    def getInstances(self):
        """
        Return the list of dictionary instances, which contains all
        combinations of the parameter values (the cartesian product).
        """
        return self.instances

    def _reconstructInstances(self):
        ""
        save_params = self.params
        self.params = []
        self.instances = []
        for names,values in save_params:
            self.addParameterGroup( names, values )


###########################################################################

def accumulate_parameter_group_list( Dlist, names, values_list ):
    """
    Performs a cartesian product with an existing list of dictionaries and a
    new name=value set.  For example, if

        Dlist = [ {'A':'a1'} ]
        names = ['B']
        values_list = [ ['b1'], ['b2'] ]

    then this list is returned

        [ {'A':'a1', 'B':'b1'},
          {'A':'a1', 'B':'b2'} ]

    An example using a group:

        Dlist = [ {'A':'a1'}, {'A':'a2'} ]
        names = ['B','C']
        values_list = [ ['b1','c1'], ['b2','c2'] ]

    would yield

        [ {'A':'a1', 'B':'b1', 'C':'c1'},
          {'A':'a1', 'B':'b2', 'C':'c2'},
          {'A':'a2', 'B':'b1', 'C':'c1'},
          {'A':'a2', 'B':'b2', 'C':'c2'} ]
    """
    newL = []
    for values in values_list:
        newL.extend( add_parameter_group_to_list_of_dicts( Dlist, names, values ) )
    return newL


def add_parameter_group_to_list_of_dicts( Dlist, names, values ):
    """
    Copies and returns the given list of dictionaries but with
    names[0]=values[0] and names[1]=values[1] etc added to each.
    """
    assert len(names) == len(values)
    N = len(names)

    new_Dlist = []

    for D in Dlist:
        newD = D.copy()
        for i in range(N):
            newD[ names[i] ] = values[i]
        new_Dlist.append( newD )

    return new_Dlist
