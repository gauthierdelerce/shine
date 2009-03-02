#!/usr/bin/env python
# Shine.Configuration.ModelFile test suite
# Written by A. Degremont 2009-10-02
# $Id$


"""Unit test for ModelFile"""

import sys
import unittest
import tempfile

sys.path.insert(0, '../lib')

from Shine.Configuration.ModelFile import *


class ModelFileTest(unittest.TestCase):

    def makeTestFile(self, text):
        """
        Create a temporary file with the provided text.
        """
        f = tempfile.NamedTemporaryFile()
        f.write(text)
        f.flush()
        return f

    def makeTestModel(self, text):
        """
        Create a temporary file instance and returns a ModelFile with it.
        """
        f = self.makeTestFile(text)
        model = ModelFile(filename=f.name)
        return model

    def testSyntaxComments(self):
        """test comment syntax"""

        model = self.makeTestModel("""

# Comments
   # Some comments with spaces
       # Some with tabs and ponctuation: toto= value
""")

        self.assertEqual(len(model.keys), 0)

    def testBasic(self):
        """test a basic key/value definition"""

        model = self.makeTestModel("\nfoo: bar\n\n")

        self.assertEqual(model.has_key('foo'), True)
        self.assertEqual(model.get('foo'), ['bar'])

    def testMultipleValues(self):
        """test multiple values for the same key"""

        model = self.makeTestModel("""
# Keys
multiple: value1
multiple: value2
""")

        self.assertEqual(model.has_key('multiple'), True)
        self.assertEqual(model.get('multiple'), ['value1', 'value2'])

    def testEmptyValue(self):
        """test empty value"""

        model = self.makeTestModel("key : \n")

        self.assertEqual(model.has_key('key'), True)
        self.assertEqual(model.get('key'), [''])

    def testTabs(self):
        """test with various tabs"""

        model = self.makeTestModel("""
# Tabs
        key_tabbed: value2
        key_tabbed2:    value_tabbed
""")

        self.assertEqual(model.has_key('key_tabbed'), True)
        self.assertEqual(model.get('key_tabbed'), ['value2'])

        self.assertEqual(model.has_key('key_tabbed2'), True)
        self.assertEqual(model.get('key_tabbed2'), ['value_tabbed'])

    def testWrongSyntax(self):
        """test different invalid syntax"""

        f = self.makeTestFile("wrong syntax line\n")
        self.assertRaises(ModelFileSyntaxError, ModelFile, filename=f.name)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(ModelFileTest)
    unittest.TextTestRunner(verbosity=2).run(suite)