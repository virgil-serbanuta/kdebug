#!/usr/bin/env python3

import sys

INDENT = '    '
CONTEXT_PREFIX = '('
CONTEXT = 'Context:'

def remove_prefix(lines, prefix, allowed):
    result = []
    for l in lines:
        if l.startswith(prefix):
            l = l[len(prefix):]
        else:
            assert l.startswith(allowed), [l, prefix, allowed]
        result.append(l)
    return result

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
        context = entries[current].context()
        if context is not None:
            if  (   len(entries[current].context()) <= context_size
                or  is_top_level(entries[current].context())
                ):
                return (current, entries[start:current])
        current += 1
    return (current, entries[start:current])

def is_top_level(context):
    for c in context:
        if not isinstance(c, GenericContext):
            return False
    return True

def checkContextPrefixList(entry, children):
    entry_context = entry.context()
    for child in children:
        child_context = child.context()
        if child_context is not None:
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

    def __repr__(self) -> str:
        return str(self)

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
                'LogMessage': GenericContext.parse,
                'LogJsonRpcServer': GenericContext.parse,
                'InfoJsonRpcProcessRequest': GenericContext.parse,
                'DebugAttemptedRewriteRules': GenericContext.parse,
                'DebugAppliedRewriteRules': GenericContext.parse,
            }
        return cls.ENTRIES

    @classmethod
    def parse(cls, line):
        assert line.startswith(CONTEXT_PREFIX), [line]
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
    @classmethod
    def parse(cls, line):
        # 'while applying equation at /home/virgil/.cache/bazel/_bazel_virgil/c0f96c7174abcbf704b5e389be3783a0/sandbox/linux-sandbox/1/execroot/__main__/protocol-correctness/proof/execution-proof-helpers.k:326:8-330:64'
        assert line.startswith(cls.LINE_PREFIX), [line]

        location = FileLocation.parse(line[len(cls.LINE_PREFIX):])
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
                'LogMessage': LogMessage.parse,
                'LogJsonRpcServer': LogJsonRpcServer.parse,
                'InfoJsonRpcProcessRequest': InfoJsonRpcProcessRequest.parse,
                'DebugAttemptedRewriteRules': DebugAttemptedRewriteRules.parse,
                'DebugAppliedRewriteRules': DebugAppliedRewriteRules.parse,
            }
        return cls.ENTRIES

    @classmethod
    def parse(cls, lines):
        assert lines
        if lines[0].startswith('  kore-rpc'):
            lines = remove_prefix(lines, '  ', CONTEXT)
        if lines[0].startswith('  kore-repl'):
            lines = remove_prefix(lines, '  ', CONTEXT)
        if not lines[0].startswith('kore-repl') and not lines[0].startswith('kore-rpc'):
            return None
        if not lines[0].endswith('):'):
            return None
        type_start = lines[0].rfind('(')
        assert type_start >= 0
        t = lines[0][type_start + 1:-2]
        if t in cls.entries():
            return cls.entries()[t](remove_prefix(lines[1:], INDENT, CONTEXT))
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
        assert not lines[current_line].startswith(CONTEXT_PREFIX)
        assert lines[current_line].startswith(DebugApplyEquation.APPLIED_PREFIX)
        current_line += 1
        kore = lines[current_line:]
        kore = remove_prefix(kore, INDENT, CONTEXT)
        assert kore
        return DebugApplyEquation(kore)

    def __init__(self, kore):
        self.__kore = kore

    def context(self):
        return None

    def kore(self):
        return self.__kore

class DebugAttemptEquation(LogEntry):
    APPLY_PREFIX = 'applying equation at '
    APPLY_SUFFIX = ' to term:'

    @staticmethod
    def parse(lines):
        assert lines

        current_line = 0
        while lines[current_line].startswith(CONTEXT_PREFIX):
            # c = Context.parse(lines[current_line])
            # assert c is not None
            # context.append(c)
            current_line += 1
        assert current_line < len(lines)

        context_start = current_line
        while context_start < len(lines):
            if lines[context_start].startswith(CONTEXT):
                break
            context_start += 1
        assert context_start < len(lines)
        context = []
        for line in lines[context_start + 1 : ]:
            c = Context.parse(line)
            assert c is not None
            context.append(c)

        if lines[current_line].startswith(DebugAttemptEquation.APPLY_PREFIX):
            assert lines[current_line].endswith(DebugAttemptEquation.APPLY_SUFFIX)
            file_location = FileLocation.parse(lines[current_line][len(DebugAttemptEquation.APPLY_PREFIX):-len(DebugAttemptEquation.APPLY_SUFFIX)])
            current_line += 1

            kore = remove_prefix(lines[current_line:context_start], INDENT, CONTEXT)
            assert kore
            return DebugAttemptEquation(context, file_location, kore)
        elif lines[current_line].startswith(EquationIsApplicable.PREFIX):
            return EquationIsApplicable(context)
        elif lines[current_line].startswith(EquationIsNotApplicable.PREFIX):
            current_line += 1
            return EquationIsNotApplicable.parse(context, lines[current_line:context_start])
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

    def __repr__(self):
        return 'DebugAttemptEquation(context=%s, equation_location=%s, term_kore=%s)' % (repr(self.__context), repr(self.__equation_location), repr(self.__term_kore))

    def __str__(self):
        return repr(self)

class EquationIsApplicable(LogEntry):
    PREFIX = 'equation is applicable'
    def __init__(self, context):
        self.__context = context

    def context(self):
        return self.__context

class EquationIsNotApplicable(LogEntry):
    PREFIX = 'equation is not applicable'

    @staticmethod
    def parse(context, lines):
        current_line = 0

        if lines[current_line].startswith(EquationIsNotApplicableRequirement.EQUATION_REQUIREMENT_PREFIX):
            return EquationIsNotApplicableRequirement.parse(context, lines)
        if lines[current_line].startswith(EquationIsNotApplicableMatch.EQUATION_MATCH_PREFIX):
            return EquationIsNotApplicableMatch.parse(context, lines)
        if lines[current_line].startswith(EquationIsNotApplicableApplyMatch.EQUATION_MATCH_PREFIX):
            return EquationIsNotApplicableApplyMatch.parse(context, lines)
        assert False, [lines[current_line]]

    # def __init__(self, context):
    #     self.__context = context

    # def context(self):
    #     return self.__context

class EquationIsNotApplicableRequirement(EquationIsNotApplicable):
    EQUATION_REQUIREMENT_PREFIX = 'Could not infer the equation requirement:'
    MATCHING_REQUIREMENT_PREFIX = 'and the matching requirement:'
    SIDE_CONDITION_PREFIX = 'from the side condition:'
    NEGATED_IMPLICATION_PREFIX = 'The negated implication is:'

    ACTUAL_SIDE_CONDITION_PREFIX = 'Assumed true condition:'
    TERM_REPLACEMENTS_PREFIX = 'TermLike replacements:'
    PREDICATE_REPLACEMENTS_PREFIX = 'Predicate replacements:'
    DEFINED_PREFIX = 'Assumed to be defined:'

    @staticmethod
    def parse(context, lines):
        current_line = 0

        assert(lines[current_line] == EquationIsNotApplicableRequirement.EQUATION_REQUIREMENT_PREFIX), lines[current_line]
        current_line += 1
        (current_line, equation_kore) = extract_indented(lines, current_line)
        equation_kore = remove_prefix(equation_kore, INDENT, CONTEXT)

        assert(lines[current_line] == EquationIsNotApplicableRequirement.MATCHING_REQUIREMENT_PREFIX), lines[current_line]
        current_line += 1
        (current_line, matching_kore) = extract_indented(lines, current_line)
        matching_kore = remove_prefix(matching_kore, INDENT, CONTEXT)

        assert(lines[current_line] == EquationIsNotApplicableRequirement.SIDE_CONDITION_PREFIX), lines[current_line]
        current_line += 1
        (current_line, side_condition) = extract_indented(lines, current_line)

        side_condition = remove_prefix(side_condition, INDENT, CONTEXT)
        current_side = 0

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicableRequirement.ACTUAL_SIDE_CONDITION_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, side_condition_kore) = extract_indented(side_condition, current_side)
        side_condition_kore = remove_prefix(side_condition_kore, INDENT, CONTEXT)

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicableRequirement.TERM_REPLACEMENTS_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, term_replacements) = extract_indented(side_condition, current_side)
        term_replacements = remove_prefix(term_replacements, INDENT, CONTEXT)

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicableRequirement.PREDICATE_REPLACEMENTS_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, predicate_replacements) = extract_indented(side_condition, current_side)
        predicate_replacements = remove_prefix(predicate_replacements, INDENT, CONTEXT)

        assert current_side < len(side_condition), [side_condition, current_side]
        assert(side_condition[current_side] == EquationIsNotApplicableRequirement.DEFINED_PREFIX), side_condition[current_side]
        current_side += 1
        (current_side, defined_terms) = extract_indented(side_condition, current_side)
        defined_terms = remove_prefix(defined_terms, INDENT, CONTEXT)

        assert(lines[current_line] == EquationIsNotApplicableRequirement.NEGATED_IMPLICATION_PREFIX), lines[current_line]
        current_line += 1
        (current_line, negated_implication) = extract_indented(lines, current_line)
        negated_implication = remove_prefix(negated_implication, INDENT, CONTEXT)

        assert current_line == len(lines), [current_line, lines[current_line], lines]

        return EquationIsNotApplicableRequirement(
            context,
            equation_kore,
            matching_kore,
            side_condition_kore, term_replacements, predicate_replacements, defined_terms,
            negated_implication)

    def __init__(self, context, equation_kore, matching_kore, side_condition_kore, term_replacements, predicate_replacements, defined_terms, negated_implication):
        self.__context = context
        self.__equation_kore = equation_kore
        self.__matching_kore = matching_kore
        self.__side_condition_kore = side_condition_kore
        self.__term_replacements = term_replacements
        self.__predicate_replacements = predicate_replacements
        self.__defined_terms = defined_terms
        self.__negated_implication = negated_implication

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

    def predicateReplacementsKore(self):
        return self.__predicate_replacements

    def definedTermsKore(self):
        return self.__defined_terms

    def negatedImplicationKore(self):
        return self.__negated_implication


class EquationIsNotApplicableMatch(EquationIsNotApplicable):
    EQUATION_MATCH_PREFIX = 'equation did not match term'

    @staticmethod
    def parse(context, lines):
        current_line = 0

        assert (lines[current_line].startswith(EquationIsNotApplicableMatch.EQUATION_MATCH_PREFIX)), [lines[current_line]]
        reason = lines[current_line][len(EquationIsNotApplicableMatch.EQUATION_MATCH_PREFIX) + 1].strip()
        current_line += 1

        if current_line != len(lines):
            if lines[current_line].startswith(CONTEXT):
                current_line = len(lines)
        assert current_line == len(lines), [current_line, lines[current_line], lines]

        return EquationIsNotApplicableMatch(context, reason)

    def __init__(self, context, reason):
        self.__context = context
        self.__reason = reason

    def context(self):
        return self.__context

    def __repr__(self):
        return 'EquationIsNotApplicableMatch(context=%s, reason=%s)' % repr(self.__context, repr(self.__reason))

class EquationIsNotApplicableApplyMatch(EquationIsNotApplicable):
    EQUATION_MATCH_PREFIX = 'could not apply match result'

    @staticmethod
    def parse(context, lines):
        current_line = 0

        assert lines[current_line].startswith(EquationIsNotApplicableApplyMatch.EQUATION_MATCH_PREFIX), lines[current_line]
        current_line += 1

        (current_line, reasons) = extract_indented(lines, current_line)
        reasons = remove_prefix(reasons, INDENT, CONTEXT)

        assert current_line == len(lines), [current_line, lines[current_line], lines]

        return EquationIsNotApplicableApplyMatch(context, reasons)

    def __init__(self, context, reasons):
        self.__context = context
        self.__reasons = reasons

    def context(self):
        return self.__context

    def reasons(self):
        return self.__reasons

class LogMessage(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return LogMessage(lines)

    def __init__(self, lines):
        self.__lines = lines

    def context(self):
        return None


class LogJsonRpcServer(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return LogJsonRpcServer(lines)

    def __init__(self, lines):
        self.__lines = lines

    def context(self):
        return None

class InfoJsonRpcProcessRequest(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return InfoJsonRpcProcessRequest(lines)

    def __init__(self, lines):
        self.__lines = lines

    def context(self):
        return None

class DebugAttemptedRewriteRules(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return DebugAttemptedRewriteRules(lines)

    def __init__(self, lines):
        self.__lines = lines

    def context(self):
        return None

class DebugAppliedRewriteRules(LogEntry):
    @staticmethod
    def parse(lines):
        assert lines
        return DebugAppliedRewriteRules(lines)

    def __init__(self, lines):
        self.__lines = lines

    def context(self):
        return None

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
        (entry, children) = entries[start]
        start += 1
        if isinstance(entry, DebugAttemptEquation):
            if start < len(entries):
                (next_entry, next_children) = entries[start]
                if isinstance(next_entry, DebugApplyEquation):
                    assert not next_children
                    assert children
                    assert isinstance(children[-1].main_entry(), EquationIsApplicable)
                    checkSameContext(entry, next_entry)
                    start += 1
                    return (start, OrganizedAppliedEquation(entry, children[:-1], children[-1], next_entry))

            assert children, [entry]
            if isinstance(children[-1].main_entry(), EquationIsNotApplicableApplyMatch):
                return (start, OrganizedNotAppliedEquationApplyMatch(entry, children[:-1], children[-1])) # 
            if isinstance(children[-1].main_entry(), EquationIsNotApplicableRequirement):
                return (start, OrganizedNotAppliedEquationRequirement(entry, children[:-1], children[-1]))
            if isinstance(children[-1].main_entry(), EquationIsNotApplicableMatch):
                assert len(children) == 1
                return (start, OrganizedNotAppliedEquationMatch(entry, children[0]))
            assert False, [entry, children[-1].main_entry()]
        elif isinstance(entry, EquationIsNotApplicableMatch):
            assert not children
            return (start, OrganizedSimple('Matching failed', entry, 'Failure computation:', children))
        elif isinstance(entry, EquationIsNotApplicableApplyMatch):
            return (start, OrganizedSimple('Failing to apply match', entry, 'Failure computation:', children))
        elif isinstance(entry, EquationIsNotApplicableRequirement):
            assert not children
            return (start, OrganizedSimple('Requirement failed', entry, 'Failure computation:', children))
        elif isinstance(entry, EquationIsApplicable):
            assert not children
            return (start, OrganizedSimple('Success', entry, 'Success computation:', children))
        elif isinstance(entry, LogMessage):
            assert not children, [children]
            return (start, OrganizedSimple('LogMessage', entry, 'No children:', children))
        elif isinstance(entry, LogJsonRpcServer):
            assert not children, [children]
            return (start, OrganizedSimple('LogJsonRpcServer', entry, 'No children:', children))
        elif isinstance(entry, InfoJsonRpcProcessRequest):
            assert not children, [children]
            return (start, OrganizedSimple('InfoJsonRpcProcessRequest', entry, 'No children:', children))
        elif isinstance(entry, DebugAttemptedRewriteRules):
            assert not children, [children]
            return (start, OrganizedSimple('DebugAttemptedRewriteRules', entry, 'No children:', children))
        elif isinstance(entry, DebugAppliedRewriteRules):
            assert not children, [children]
            return (start, OrganizedSimple('DebugAppliedRewriteRules', entry, 'No children:', children))
        elif isinstance(entry, DebugApplyEquation):
            assert not children, [children]
            return (start, OrganizedSimple('DebugApplyEquation', entry, 'No children:', children))
        else:
            assert False, [type(entry), start, entry]

    def _indent(self, indent, out):
        for _ in range(0, indent):
            out.append(INDENT)

    def _writeKore(self, kore, indent, out):
        for line in kore:
            self._indent(indent, out)
            out.append(line)
            out.append('\n')

class OrganizedSimple(Organized):
    def __init__(self, description, entry, children_description, children):
        self.__description = description
        self.__entry = entry
        self.__children_description = children_description
        self.__children = children

    def main_entry(self):
        return self.__entry

    def write(self, context_start, indent, out):
        self._indent(indent, out)
        out.append(self.__description)
        out.append('\n')
        indent += 1

        self._indent(indent, out)
        out.append("Context:\n")
        context = self.__entry.context()
        for i in range(context_start, len(context)):
            self._indent(indent + 1, out)
            context[i].write(out)
            out.append('\n')

        self._indent(indent, out)
        out.append(self.__children_description)
        out.append('\n')

        for c in self.__children:
            c.write(len(context) + 1, indent + 1, out)

    def writeChildren(self, context_start, indent, out):
        for c in self.__children:
            c.write(context_start, indent, out)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return f'Organized({[self.__description]}, {[self.__entry]})'


class OrganizedAppliedEquation(Organized):
    def __init__(self, debug_attempt_equation, children, debug_apply_equation, result):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__children = children
        self.__debug_apply_equation = debug_apply_equation
        self.__result = result

    def main_entry(self):
        return self.__debug_attempt_equation

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

class OrganizedNotAppliedEquationRequirement(Organized):
    def __init__(self, debug_attempt_equation, children, debug_not_apply_equation):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__children = children
        self.__debug_not_apply_equation = debug_not_apply_equation.main_entry()

    def main_entry(self):
        return self.__debug_attempt_equation

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
        out.append('Predicate replacements:\n')
        self._writeKore(self.__debug_not_apply_equation.predicateReplacementsKore(), indent + 2, out)

        self._indent(indent + 1, out)
        out.append('Assumed to be defined:\n')
        self._writeKore(self.__debug_not_apply_equation.definedTermsKore(), indent + 2, out)

        self._indent(indent, out)
        out.append("Computation:\n")
        for c in self.__children:
            c.write(len(context) + 1, indent + 1, out)

class OrganizedNotAppliedEquationMatch(Organized):
    def __init__(self, debug_attempt_equation, debug_not_apply_equation):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__debug_not_apply_equation = debug_not_apply_equation

    def main_entry(self):
        return self.__debug_attempt_equation

    def write(self, context_start, indent, out):
        self._indent(indent, out)
        out.append("Not applying equation, matching failed:\n")
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
        out.append("Matching computation:\n")
        self.__debug_not_apply_equation.writeChildren(len(context) + 1, indent + 1, out)

class OrganizedNotAppliedEquationApplyMatch(Organized):
    def __init__(self, debug_attempt_equation, children, debug_not_apply_equation):
        self.__debug_attempt_equation = debug_attempt_equation
        self.__children = children
        self.__debug_not_apply_equation = debug_not_apply_equation.main_entry()

    def main_entry(self):
        return self.__debug_attempt_equation

    def write(self, context_start, indent, out):
        self._indent(indent, out)
        out.append("Not applying equation, matching failed:\n")
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
        out.append("Computation:\n")
        for c in self.__children:
            c.write(len(context) + 1, indent + 1, out)

        self._indent(indent, out)
        out.append("Matching failure reasons:\n")
        for reason in self.__debug_not_apply_equation.reasons():
            self._indent(indent + 1, out)
            out.append(reason)
            out.append('\n')

def parse(contents):
    lines = contents.split('\n')
    entries = []
    current_lines = []
    for line in lines:
        if not line:
            continue
        if not line.startswith(INDENT) and not line.startswith(CONTEXT):
            if current_lines:
                # print(current_lines)
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

def lenNull(ctx):
    if ctx is None:
        return 1000
    return len(ctx)

def parseFunctionApplication(entries):
    start = 0
    preparsed = []
    while start < len(entries):
        entry = entries[start]
        start += 1
        if entry.context() is None:
            preparsed.append((entry, []))
            continue
        (start, children) = extract_inner_entries(entries, start, lenNull(entry.context()))
        checkContextPrefixList(entry, children)
        parsed_children = parseFunctionApplication(children)

        preparsed.append((entry, parsed_children))

    start = 0
    results = []
    while start < len(preparsed):
        (start, result) = Organized.parse(preparsed, start)
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
