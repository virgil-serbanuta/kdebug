#!/usr/bin/env python3

import sys

def normalize(lines):
  return transform(parse(lines))

def transformTraversal(lines, visitor):
  retv = []

  for item in lines:
    if type(item) == list:
      retv.append(transformTraversal(item, visitor))
    else:
      retv.append(item)

  visited = visitor(retv)
  if visited is not None:
    return visited
  return retv

def transformAnd(lines):
  i = 0
  retv = []
  while i < len(lines):
    line = lines[i]
    i += 1
    retv.append(line)

    if line != '#And':
      continue
    assert i < len(lines)
    assert type(lines[i]) == list
    if i + 1 < len(lines) and lines[i + 1] != '#And':
      continue
    if len(lines[i]) != 1:
      continue
    assert type(lines[i][0]) == str
    retv[-1] = '#And ' + lines[i][0]
    i += 1
  return retv

def transformJoin(lines):
  if len(lines) < 2:
    return None
  for l in lines:
    if not type(l) == str:
      return None
  lines = [l.strip() for l in lines]
  return [' '.join(lines)]

def transformEquals(lines):
  if len(lines) != 3:
    return None
  if lines[1] != '#Equals':
    return None
  assert type(lines[0]) == list
  assert type(lines[2]) == list
  first = lines[0]
  second = lines[2]
  assert len(first) == 1, lines
  assert len(second) == 1, lines
  first = first[0]
  second = second[0]
  assert type(first) == str
  assert type(second) == str
  return ['%s :==: %s' % (first, second)]

def transformBracketed(lines, visitor):
  if len(lines) < 2:
    return None
  if lines[0] == '{' or lines == '}':
    return visitor(lines[ 1 : -1 ])
  if not type(lines[0]) == str or not type(lines[-1]) == str:
    return None
  if not lines[0].endswith('{') or not lines[-1].startswith('}'):
    return None
  visited = visitor(lines[ 1 : -1 ])
  if visited is None:
    return None
  return [lines[0][:-1].strip(), visited, lines[-1][1:].strip()]

def transform(lines):
  lines = transformTraversal(lines, transformJoin)
  lines = transformTraversal(lines, transformEquals)
  lines = transformTraversal(lines, lambda l : transformBracketed(l, transformEquals))
  lines = transformTraversal(lines, transformAnd)
  return lines

def parse(lines):
  with_level = []
  for line in lines:
    line = line.rstrip()
    stripped = line.strip()
    with_level.append((len(line) - len(stripped), stripped))

  return parseLevelled(with_level)

def normalizeLevel(lines):
  if not lines:
    return lines
  min_level = min([level for (level, _) in lines])
  return [(level - min_level, line) for (level, line) in lines]

def parseLevelled(lines):
  lines = normalizeLevel(lines)
  parsed = []
  children = []
  for (level, line) in lines:
    if level > 0:
      children.append((level, line))
    else:
      if children:
        parsed.append(parseLevelled(children))
      parsed.append(line)
      children = []
  if children:
    parsed.append(parseLevelled(children))

  return parsed

def main(argv):
  print(normalize([
    '    true',
    '  #Equals',
    '    true',
    '#And',
    '  {',
    '    true',
    '  #Equals',
    '    true',
    '  }',
  ]))

if __name__ == '__main__':
  main(sys.argv[1:])
