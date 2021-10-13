#!/usr/bin/env python3

import filesequence
import sys

def readFile(name):
  with open(name, "r") as f:
    return [l[:len(l) - 1] for l in f]

def replaceReferrences(lines):
  replaced = []
  for line in lines:
    last_space = line.rfind(' ')
    if last_space < 0:
      replaced.append(line)
      continue
    try:
      equation = filesequence.findSequenceFromText(line[last_space + 1:], ' ')
      replaced.append('%s%s' % (line[:last_space + 1], equation))
    except Exception:
      replaced.append(line)
  return replaced

def main(argv):
  if len(argv) != 1:
    print('Usage: extract-equation-rules.py log-file')
    return
  lines = readFile(argv[0])
  print('\n'.join(replaceReferrences(lines)))

if __name__ == "__main__":
    main(sys.argv[1:])
