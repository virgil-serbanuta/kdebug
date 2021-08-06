#!/usr/bin/env python3

import sys

INDENT = '    '
CONTEXT_PREFIX = '('

def remove_prefix(lines, prefix):
    for l in lines:
        assert l.startswith(prefix)
    return [l[len(prefix):] for l in lines]

def extract_indented(lines, start):
    current = start
    while current < len(lines):
        if not lines[current].startswith(INDENT):
            return (current, lines[start:current])
        current += 1
    return (current, lines[start:current])

def extract_inner_entries(entries, start, context_size):
    current = start
    while current < len(entries):
        if len(entries[current].context()) <= context_size:
            return (current, entries[start:current])
        current += 1
    return (current, entries[start:current])

def checkContextPrefixList(entry, children):
    entry_context = entry.context()
    for child in children:
        child_context = child.context()
        assert len(entry_context) < len(child_context), [entry_context, child_context]
        for (ec, cc) in zip(entry_context, child_context):
            assert ec == cc, [ec, cc, entry_context, child_context]

def checkSameContext(entry1, entry2):
    context1 = entry1.context()
    context2 = entry2.context()
    assert(len(context1) == len(context2)), [context2, context2]
    for (ec, cc) in zip(context1, context2):
        assert ec == cc, [ec, cc, context1, context2]

class FileLocation(object):
    @staticmethod
    def parse(line):
        end = line.find(':')
        assert end >= 0, [line]
        file_name = line[:end]
        end1 = line.find(':', end + 1)
        assert end1 >= 0, [line]
        start_line = int(line[end + 1: end1])
        end = end1
        end1 = line.find('-', end + 1)
        if end1 >= 0:
            assert end1 >= 0, [line]
            start_column = int(line[end + 1: end1])
            end = end1
            end1 = line.find(':', end + 1)
            assert end1 >= 0, [line]
            end_line = int(line[end + 1: end1])
            end_column = int(line[end1 + 1:])
        else:
            start_column = int(line[end + 1:])
            end_line = -1
            end_column = -1
        return FileLocation(file_name, start_line, start_column, end_line, end_column)

    def __init__(self, file_name, start_line, start_column, end_line, end_column):
        self.__file_name = file_name
        self.__start_line = start_line
        self.__start_column = start_column
        self.__end_line = end_line
        self.__end_column = end_column

    def __str__(self):
        if self.__end_line < 0:
            return "%s:%d:%d" % (self.__file_name, self.__start_line, self.__start_column)
        return "%s:%d:%d-%d:%d" % (self.__file_name, self.__start_line, self.__start_column, self.__end_line, self.__end_column)

class Context(object):
    ENTRIES = {}

    @classmethod
    def entries(cls):
        if not cls.ENTRIES:
            cls.ENTRIES = {
                'InfoReachability': GenericContext.parse,
                'InfoAttemptUnification': GenericContext.parse,
                'DebugAttemptEquation': DebugAttemptEquationContext.parse,
            }
        return cls.ENTRIES

    @classmethod
    def parse(cls, line):
        assert line.startswith(CONTEXT_PREFIX)
        type_end = line.find(')')
        assert type_end >= 0
        assert type_end + 1 < len(line)
        assert line[type_end + 1] == ' '
        t = line[len(CONTEXT_PREFIX):type_end]
        if t in cls.entries():
            return cls.entries()[t](line[type_end + 2:])
        assert False, [t]
        return GenericContext.parse(line[type_end + 2:])

    def __repr__(self):
        return "'%s'" % str(self)

    def __eq__(self, other):
        # TODO: Something better.
        return repr(self) == repr(other)

class GenericContext(Context):
    @staticmethod
    def parse(line):
        return GenericContext(line)

    def __init__(self, line):
        self.__line = line

    def __str__(self):
        return self.__line

    def write(self, out):
        out.append(self.__line)

class DebugAttemptEquationContext(Context):
    LINE_PREFIX = 'while applying equation at '
    LINE_SUFFIX = ':'
    @classmethod
    def parse(cls, line):
        # 'while applying equation at /home/virgil/.cache/bazel/_bazel_virgil/c0f96c7174abcbf704b5e389be3783a0/sandbox/linux-sandbox/1/execroot/__main__/protocol-correctness/proof/execution-proof-helpers.k:326:8-330:64:'
        assert line.startswith(cls.LINE_PREFIX), [line]
        assert line.endswith(cls.LINE_SUFFIX), [line]

        location = FileLocation.parse(line[len(cls.LINE_PREFIX):-len(cls.LINE_SUFFIX)])
        assert location is not None
        return DebugAttemptEquationContext(location)

    def __init__(self, location):
        self.__location = location

    def __str__(self):
        return "Applying equation at: %s" % self.__location

    def write(self, out):
        out.append(str(self))

class LogEntry(object):
    ENTRIES = {}

    @classmethod
    def entries(cls):
        if not cls.ENTRIES:
            cls.ENTRIES = {
                'DebugApplyEquation': DebugApplyEquation.parse,
                'DebugAttemptEquation': DebugAttemptEquation.parse,
            }
        return cls.ENTRIES

    @classmethod
    def parse(cls, lines):
        assert lines
        if lines[0].startswith('  kore-repl'):
            lines = remove_prefix(lines, '  ')
        if not lines[0].startswith('kore-repl'):
            return None
        if not lines[0].endswith('):'):
            return None
        type_start = lines[0].rfind('(')
        assert type_start >= 0
        t = lines[0][type_start + 1:-2]
        if t in cls.entries():
            return cls.entries()[t](remove_prefix(lines[1:], INDENT))
        assert False, [t]
        return GenericLogEntry(lines[1:])

    def write(self, out):
        assert False, type(self)

    def context(self):
        assert False, type(self)

class DebugApplyEquation(LogEntry):
    APPLIED_PREFIX = 'applied equation at '

    @staticmethod
    def parse(lines):
        assert lines

        current_line = 0
        context = []
        while lines[current_line].startswith(CONTEXT_PREFIX):
            c = Context.parse(lines[current_line])
            assert c is not None
            context.append(c)
            current_line += 1
        assert lines[current_line].startswith(DebugApplyEquation.APPLIED_PREFIX)
        current_line += 1
        kore = lines[current_line:]
        kore = remove_prefix(kore, INDENT)
        assert kore
        return DebugApplyEquation(context, kore)

    def __init__(self, context, kore):
        self.__context = context
        self.__kore = kore

    def context(self):
        return self.__context

    def kore(self):
        return self.__kore

class DebugAttemptEquation(LogEntry):
    APPLY_PREFIX = 'applying equation at '
    APPLY_SUFFIX = ' to term:'

    @staticmethod
    def parse(lines):
        assert lines

        current_line = 0
        context = []
        while lines[current_line].startswith(CONTEXT_PREFIX):
            c = Context.parse(lines[current_line])
            assert c is not None
            context.append(c)
            current_line += 1
        assert current_line < len(lines)

        if lines[current_line].startswith(DebugAttemptEquation.APPLY_PREFIX):
            assert lines[current_line].endswith(DebugAttemptEquation.APPLY_SUFFIX)
            file_location = FileLocation.parse(lines[current_line][len(DebugAttemptEquation.APPLY_PREFIX):-len(DebugAttemptEquation.APPLY_SUFFIX)])
            current_line += 1

            kore = remove_prefix(lines[current_line:], INDENT)
            assert kore
            return DebugAttemptEquation(context, file_location, kore)
        elif lines[current_line].startswith(EquationIsApplicable.PREFIX):
            return EquationIsApplicable(context)
        elif lines[current_line].startswith(EquationIsNotApplicable.PREFIX):
            current_line += 1
            return EquationIsNotApplicable.parse(context, lines[current_line:])
        else:
            assert False, [lines[current_line]]

    def __init__(self, context, equation_location, term_kore):
        self.__context = context
        self.__equation_location = equation_location
        self.__term_kore = term_kore

    def context(self):
        return self.__context

    def equationLocation(self):
        return self.__equation_location

    def termKore(self):
        return self.__term_kore

class EquationIsApplicable(LogEntry):
    PREFIX = 'equation is applicable'
    def __init__(self, context):
        self.__context = context

    def context(self):
        return self.__context

class EquationIsNotApplicable(LogEntry):
    PREFIX = 'equation is not applicable'

    EQUATION_REQUIREMENT_PREFIX = 'could not infer the equation requirement:'
    MATCHING_REQUIREMENT_PREFIX = 'and the matching requirement:'
    SIDE_CONDITION_PREFIX = 'from the side condition:'

    ACTUAL_SIDE_CONDITION_PREFIX = 'Assumed true condition:'
    TERM_REPLACEMENTS_PREFIX = 'Term replacements:'
    DEFINED_PREFIX = 'Assumed to be defined:'

    @staticmethod
    def parse(context, lines):
        current_line = 0

        assert(lines[current_line] == EquationIsNotApplicable.EQUATION_REQUIREMENT_PREFIX), lines[current_line]
        current_line += 1
        (current_line, equation_kore) = extract_indented(lines, current_line)
        equation_kore = remove_prefix(equation_kore, INDENT)

        assert(lines[current_line] == EquationIsNotApplicable.MATCHING_REQUIREMENT_PREFIX), lines[current_line]
        current_line += 1
        (current_line, matching_kore) = extract_indented(lines, current_line)
        matching_kore = remove_prefix(matching_kore, INDENT)

        assert(lines[current_line] == EquationIsNotApplicable.SIDE_CONDITION_PREFIX), lines[current_line]
        current_line += 1
        (current_line, side_condition) = extract_indented(lines, current_line)

        assert current_line == len(lines), lines

        side_condition = remove_prefix(side_condition, INDENT)
        current_side = 0

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicable.ACTUAL_SIDE_CONDITION_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, side_condition_kore) = extract_indented(side_condition, current_side)
        side_condition_kore = remove_prefix(side_condition_kore, INDENT)

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicable.TERM_REPLACEMENTS_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, term_replacements) = extract_indented(side_condition, current_side)
        term_replacements = remove_prefix(term_replacements, INDENT)

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicable.DEFINED_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, defined_terms) = extract_indented(side_condition, current_side)
        defined_terms = remove_prefix(defined_terms, INDENT)

        return EquationIsNotApplicable(context, equation_kore, matching_kore, side_condition_kore, term_replacements, defined_terms)

    def __init__(self, context, equation_kore, matching_kore, side_condition_kore, term_replacements, defined_terms):
        self.__context = context
        self.__equation_kore = equation_kore
        self.__matching_kore = matching_kore
        self.__side_condition_kore = side_condition_kore
        self.__term_replacements = term_replacements
        self.__defined_terms = defined_terms

    def context(self):
        return self.__context

    def requiresKore(self):
        return self.__equation_kore

    def matchingKore(self):
        return self.__matching_kore

    def sideConditionKore(self):
        return self.__side_condition_kore

    def termReplacementsKore(self):
        return self.__term_replacements

    def definedTermsKore(self):
        return self.__defined_terms

class GenericLogEntry(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return GenericLogEntry(lines)

    def __init__(self, lines):
        self.__lines = lines

class Organized(object):
    @staticmethod
    def parse(entries, start):
        assert start <= len(entries)
        entry = entries[start]
        start += 1
        if isinstance(entry, DebugAttemptEquation):
            (start, children) = extract_inner_entries(entries, start, len(entry.context()))
            checkContextPrefixList(entry, children)
            parsed_children = parseFunctionApplication(children[:-1])
            if start < len(entries):
                result = entries[start]
                if isinstance(result, DebugApplyEquation):
                    assert isinstance(children[-1], EquationIsApplicable)
                    checkSameContext(entry, result)
                    start += 1
                    return (start, OrganizedAppliedEquation(entry, parsed_children, children[-1], result))
            assert isinstance(children[-1], EquationIsNotApplicable)
            return (start, OrganizedNotAppliedEquation(entry, parsed_children, children[-1]))
        else:
            assert False, type(entry)

    def _indent(self, indent, out):
        for _ in range(0, indent):
            out.append(INDENT)

    def _writeKore(self, kore, indent, out):
        for line in kore:
            self._indent(indent, out)
            out.append(line)
            out.append('\n')

class OrganizedAppliedEquation(Organized):
    def __init__(self, debug_attempt_equation, children, debug_apply_equation, result):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__children = children
        self.__debug_apply_equation = debug_apply_equation
        self.__result = result

    def write(self, context_start, indent, out):
        self._indent(indent, out)
        out.append("Applying equation:\n")
        indent += 1

        self._indent(indent, out)
        out.append("Context:\n")
        context = self.__debug_attempt_equation.context()
        for i in range(context_start, len(context)):
            self._indent(indent + 1, out)
            context[i].write(out)
            out.append('\n')

        self._indent(indent + 1, out)
        out.append('Current equation: ')
        out.append(str(self.__debug_attempt_equation.equationLocation()))
        out.append('\n')

        self._indent(indent, out)
        out.append("Term:\n")
        self._writeKore(self.__debug_attempt_equation.termKore(), indent + 1, out)

        self._indent(indent, out)
        out.append("Result:\n")
        self._writeKore(self.__result.kore(), indent + 1, out)

        self._indent(indent, out)
        out.append("Computation:\n")
        for c in self.__children:
            c.write(len(context) + 1, indent + 1, out)

class OrganizedNotAppliedEquation(Organized):
    def __init__(self, debug_attempt_equation, children, debug_not_apply_equation):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__children = children
        self.__debug_not_apply_equation = debug_not_apply_equation

    def write(self, context_start, indent, out):
        self._indent(indent, out)
        out.append("Not applying equation:\n")
        indent += 1

        self._indent(indent, out)
        out.append("Context:\n")
        context = self.__debug_attempt_equation.context()
        for i in range(context_start, len(context)):
            self._indent(indent + 1, out)
            context[i].write(out)
            out.append('\n')

        self._indent(indent + 1, out)
        out.append('Current equation: ')
        out.append(str(self.__debug_attempt_equation.equationLocation()))
        out.append('\n')

        self._indent(indent, out)
        out.append("Term:\n")
        self._writeKore(self.__debug_attempt_equation.termKore(), indent + 1, out)

        self._indent(indent, out)
        out.append('Requirement:\n')
        self._writeKore(self.__debug_not_apply_equation.requiresKore(), indent + 1, out)

        self._indent(indent, out)
        out.append('Matching condition:\n')
        self._writeKore(self.__debug_not_apply_equation.matchingKore(), indent + 1, out)

        self._indent(indent, out)
        out.append('Side condition:\n')
        self._indent(indent + 1, out)
        out.append('Assumed true:\n')
        self._writeKore(self.__debug_not_apply_equation.sideConditionKore(), indent + 2, out)

        self._indent(indent + 1, out)
        out.append('Term replacements:\n')
        self._writeKore(self.__debug_not_apply_equation.termReplacementsKore(), indent + 2, out)

        self._indent(indent + 1, out)
        out.append('Assumed to be defined:\n')
        self._writeKore(self.__debug_not_apply_equation.definedTermsKore(), indent + 2, out)

        self._indent(indent, out)
        out.append("Computation:\n")
        for c in self.__children:
            c.write(len(context) + 1, indent + 1, out)

def parse(contents):
    lines = contents.split('\n')
    entries = []
    current_lines = []
    for line in lines:
        if not line:
            continue
        if not line.startswith(INDENT):
            if current_lines:
                entry = LogEntry.parse(current_lines)
                assert entry is not None, current_lines
                entries.append(entry)
                current_lines = []
        current_lines.append(line)
    if current_lines:
        entry = LogEntry.parse(current_lines)
        assert entry is not None, current_lines
        entries.append(entry)
    return entries

def parseFunctionApplication(entries):
    start = 0
    results = []
    while start < len(entries):
        (start, result) = Organized.parse(entries, start)
        results.append(result)
    return results

def writeLog(entries, out):
    for e in entries:
        e.write(0, 0, out)
        out.append('\n')

def main(argv):
    if len(argv) != 2:
        print('Usage:\n    logparser.py input-file output-file')
        sys.exit(1)
    with open(argv[0], 'r') as f:
        contents = f.read()
    entries = parse(contents)
    organized = parseFunctionApplication(entries)

    out = []
    writeLog(organized, out)
    with open(argv[1], 'w') as f:
        f.write(''.join(out))

if __name__ == '__main__':
    main(sys.argv[1:])
