#!/usr/bin/env python3

import sys

def readFile(name):
  with open(name, "r") as f:
    return [l[:len(l) - 1] for l in f]

def findSequence(file_name, start_line, start_column, end_line, end_column, separator):
  lines = readFile(file_name)
  lines = lines[start_line - 1:end_line]
  lines[-1] = lines[-1][:end_column]
  lines[0] = lines[0][start_column - 1:]
  return separator.join(lines)

def parsePosition(arg):
  separator = arg.find(':')
  assert separator > 0
  file_name = arg[:separator]
  arg = arg[separator + 1:]
  separator = arg.find(':')
  assert separator > 0
  start_line = int(arg[:separator])
  arg = arg[separator + 1:]
  separator = arg.find('-')
  assert separator > 0
  start_column = int(arg[:separator])
  arg = arg[separator + 1:]
  separator = arg.find(':')
  assert separator > 0
  end_line = int(arg[:separator])
  end_column = int(arg[separator + 1:])
  return (file_name, start_line, start_column, end_line, end_column)

def findSequenceFromText(arg, separator):
  file_name, start_line, start_column, end_line, end_column = parsePosition(arg)
  return findSequence(file_name, start_line, start_column, end_line, end_column, separator)

def main(argv):
  if len(argv) != 1:
    print('Usage: filesequence.py input-file:line:column-line:column')
    return
  print(findSequenceFromText(argv[0], '\n'))

if __name__ == "__main__":
    main(sys.argv[1:])
