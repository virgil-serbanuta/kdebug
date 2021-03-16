#!/usr/bin/env python3

import sys

INDENT_SIZE = 2

INDENTS = [' ' * (indent * INDENT_SIZE) for indent in range(0, 100)]

# TODO: Remove the one in konfig.py
def transformTraversal(level, lines, visitor):
  retv = []

  for item in lines:
    if type(item) == list:
      retv.append(transformTraversal(level + 1, item, visitor))
    else:
      visited = visitor(level, item)
      if visited is not None:
        retv += visited
      else:
        retv.append(item)

  visited = visitor(level, retv)
  if visited is not None:
    return visited
  return retv

def splitOutsideParentheses(s, substr):
  open_r = 0
  open_s = 0
  open_c = 0
  start = 0
  retv = []
  end = s.find(substr, start)
  pos = start
  while end >= 0:
    while pos < end:
      if s[pos] == '(':
        open_r += 1
      elif s[pos] == '[':
        open_s += 1
      elif s[pos] == '{':
        open_c += 1
      elif s[pos] == ')':
        open_r -= 1
      elif s[pos] == ']':
        open_s -= 1
      elif s[pos] == '}':
        open_c -= 1
      pos += 1
    next = end + len(substr)
    if open_r == 0 and open_s == 0 and open_c == 0:
      retv.append(s[start:end])
      start = next
    end = s.find(substr, next)
  retv.append(s[start:])
  return retv

def splitKCell(max_len, level, lines):
  if type(lines) != list:
    return None
  if len(lines) < 3:
    return None
  i = 0 
  while i < len(lines) and lines[i] != '<k>':
    i += 1
  if i >= len(lines):
    return None
  assert i + 2 < len(lines)
  assert lines[i+2] == '</k>', lines[i+2]
  retv = lines[:i+1]
  retv_line = []
  assert type(lines[i+1]) == list, lines[i+1]
  for line in lines[i+1]:
    if type(line) != str:
      retv_line.append(line)
      continue
    if len(line) + level * INDENT_SIZE < max_len:
      retv_line.append(line)
      continue
    if not ' ~> ' in line:
      retv_line.append(line)
      continue
    split = splitOutsideParentheses(line, ' ~> ')
    retv_line.append(split[0])
    retv_line += ['~> ' + s for s in split[1:]]
  retv.append(retv_line)

  retv += lines[i+2:]
  return [retv]

def findParenthesesPair(s, start):
  while start < len(s) and s[start] not in '([{':
    start += 1
  if start >= len(s):
    return None
  open = [s[start]]
  split_points = []
  end = start + 1
  while end < len(s) and open:
    current = s[end]
    end += 1
    if current == ',':
      if len(open) == 1:
        split_points.append(end)
    elif current == ')':
      assert open[-1] == '('
      open.pop()
    elif current == ']':
      assert open[-1] == '['
      open.pop()
    elif current == '}':
      assert open[-1] == '{'
      open.pop()
    elif current in '([{':
      open.append(current)

  if open:
    return None
  return (start, end - 1, split_points)

def onlySpaces(start, end, str):
  for i in range(start, end + 1):
    if str[i] != ' ':
      return False
  return True

def splitParentheses(max_len, level, item):
  if type(item) != str:
    return None
  if len(item) + level * INDENT_SIZE < max_len:
    return None
  retv = []
  parens = findParenthesesPair(item, 0)
  start = 0
  while not parens is None:
    (first, last, split_points) = parens
    assert first < last
    parens = findParenthesesPair(item, last + 1)

    if onlySpaces(first + 1, last - 1, item):
      continue

    if last - start + level * INDENT_SIZE < max_len:
      if parens is None:
        retv.append(item[start:last + 1])
        retv.append(item[last + 1:])
        start = len(item)
        continue
      (nextFirst, _, _) = parens
      if nextFirst - start + level * INDENT_SIZE >= max_len:
        retv.append(item[start:last + 1])
        start = last + 1
      continue
    
    retv.append(item[start:first + 1])
    pos = first + 1
    indented = []
    for p in split_points:
      indented.append(item[pos:p])
      pos = p
    '''
    if last + 1 == len(item):
      indented.append(item[pos:last + 1])
      start = last + 1
    else:
      indented.append(item[pos:last])
      start = last
    '''
    indented.append(item[pos:last])
    start = last

    retv.append(indented)

  if not retv:
    return None
  if start < len(item):
    retv.append(item[start:])
  return retv

def strip(item):
  if type(item) != str:
    return None
  return [item.strip()]

def removeEmptyLines(item):
  if item:
    return None
  return []

def split(lines, max_len):
  lines = transformTraversal(0, lines, lambda level, l: splitKCell(max_len, level, l))
  lines = transformTraversal(0, lines, lambda _, l: strip(l))
  lines = transformTraversal(0, lines, lambda level, l: splitParentheses(max_len, level, l))
  lines = transformTraversal(0, lines, lambda _, l: strip(l))
  lines = transformTraversal(0, lines, lambda level, l: splitParentheses(max_len, level, l))
  lines = transformTraversal(0, lines, lambda _, l: strip(l))
  lines = transformTraversal(0, lines, lambda level, l: splitParentheses(max_len, level, l))
  lines = transformTraversal(0, lines, lambda _, l: strip(l))
  lines = transformTraversal(0, lines, lambda _, l: removeEmptyLines(l))
  return lines

def unparse(indent, lines, output):
  for item in lines:
    if type(item) == list:
      unparse(indent + 1, item, output)
    else:
      output.append(INDENTS[indent] + item)

def main(argv):
  print(split([
    '<k>',
    ['stuff1 ~> stuff2 ~> f(a ~> .K) + stuff3(really, big(argument), list, with[all, sorts, of, stuff in, it, hope, it, will, be, split] + 10) ~> stuff4 ~> stuff5 ~> stuff6 ~> stuff7 ~> stuff8'],
    '</k>',
  ], 30))

if __name__ == '__main__':
  main(sys.argv[1:])
