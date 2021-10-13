#!/usr/bin/env python3

import sys

class TagAttribute(object):
  def __init__(self, name, value = None):
    self.__name = name
    self.__value = value

  def name(self):
    return self.__name

  def __str__(self):
    if self.__value:
      return '%s=%s' % (self.__name, self.__value)
    return self.name

class TagOpen(object):
  def __init__(self, name, attributes):
    assert name
    self.__name = name
    self.__attributes = attributes

  def __str__(self):
    if self.__attributes:
      return '<%s %s>' % (self.__name, ' '.join([str(a) for a in self.__attributes]))
    return '<%s>' % self.__name

  def name(self):
    return self.__name

class TagOpenClose(object):
  def __init__(self, name, attributes):
    assert name
    self.__name = name
    self.__attributes = attributes

  def __str__(self):
    if self.__attributes:
      return '<%s %s/>' % (self.__name, ' '.join([str(a) for a in self.__attributes]))
    return '<%s/>' % self.__name

  def name(self):
    return self.__name

class TagClose(object):
  def __init__(self, name):
    assert name
    self.__name = name

  def __str__(self):
    return '</%s>' % self.__name

  def name(self):
    return self.__name

class SpecialTag(object):
  def __init__(self, text):
    self.__text = text

  def __str__(self):
    return self.__text

class Position(object):
  def __init__(self):
    self.__line = 1
    self.__column = 1

  def processChar(self, c):
    if c == '\n':
      self.__line += 1
      self.__column = 1
    else:
      self.__column += 1

  def __str__(self):
    return '%d:%d' % (self.__line, self.__column)

def isAttributeNameChar(c):
  return c.isalpha() or c in ':-'

def parseTags(content):
  START = 0
  LT = 1
  LT_EXCLAMATION = 2
  LT_EXCLAMATION_MINUS = 3
  COMMENT = 4
  COMMENT_MINUS = 5
  COMMENT_MINUS_MINUS = 6
  TAG_NAME = 7
  TAG_INNER = 8
  TAG_ATTRIBUTE = 9
  TAG_ATTRIBUTE_EQUALS = 10
  TAG_ATTRIBUTE_EQUALS_VALUE = 11
  TAG_CLOSE = 13
  TAG_CLOSE_NAME = 14
  TAG_AUTOCLOSE = 15
  TAG_ATTRIBUTE_SPACE = 16
  SPECIAL_TAG = 17
  SPECIAL_TAG_STRING = 18

  state = START
  text_start = 0
  tag_name_start = 0
  text_chunks = []
  tag_name = ''
  tag_attributes = []
  attribute_name_start = 0
  special_tag_start = 0
  special_tag_string_ending = ''
  position = Position()
  for pos in range(0, len(content)):
    c = content[pos]
    if state == START:
      if c == '<':
        text_chunks.append(content[text_start:pos])
        state = LT
    elif state == LT:
      if c == '!':
        state = LT_EXCLAMATION
      elif c == '?':
        state = SPECIAL_TAG
      elif c.isalpha():
        yield ''.join(text_chunks)
        text_chunks = []
        state = TAG_NAME
        tag_name_start = pos
        tag_name = ''
        tag_attributes = []
        attribute_name = ''
        attribute_name_start = 0
      elif c == '/':
        yield ''.join(text_chunks)
        text_chunks = []
        state = TAG_CLOSE
      else:
        raise Exception("Unknown char after <: '%s' (%s)" % (c, position))
    elif state == LT_EXCLAMATION:
      if c == '-':
        state = LT_EXCLAMATION_MINUS
      elif c.isalpha():
        yield ''.join(text_chunks)
        text_chunks = []
        special_tag_start = pos - 2
        state = SPECIAL_TAG
      else:
        raise Exception("Unknown char after <!: '%s' (%s)" % (c, position))
    elif state == LT_EXCLAMATION_MINUS:
      if c == '-':
        state = COMMENT
      else:
        raise Exception("Unknown char after <!-: '%s' (%s)" % (c, position))
    elif state == COMMENT:
      if c == '-':
        state = COMMENT_MINUS
    elif state == COMMENT_MINUS:
      if c == '-':
        state = COMMENT_MINUS_MINUS
      else:
        state = COMMENT
    elif state == COMMENT_MINUS_MINUS:
      if c == '>':
        state = START
        text_start = pos + 1
      elif c == '-':
        pass
      else:
        state = COMMENT
    elif state == TAG_NAME:
      if c.isalpha():
        pass
      elif c.isspace():
        tag_name = content[tag_name_start:pos]
        state = TAG_INNER
      elif c == '/':
        state = TAG_AUTOCLOSE
      elif c == '>':
        yield TagOpen(content[tag_name_start:pos], [])
        state = START
        text_start = pos + 1
        text_chunks = []
      else:
        raise Exception("Unknown char after tag name: '%s' (%s)" % (c, position))
    elif state == TAG_INNER:
      if isAttributeNameChar(c):
        attribute_name_start = pos
        attribute_name = ''
        state = TAG_ATTRIBUTE
      elif c.isspace():
        pass
      elif c == '/':
        state = TAG_AUTOCLOSE
      elif c == '>':
        yield TagOpen(tag_name, tag_attributes)
        state = START
        text_start = pos + 1
        text_chunks = []
      else:
        raise Exception("Unknown char inside tag: '%s' (%s)" % (c, position))
    elif state == TAG_ATTRIBUTE:
      if isAttributeNameChar(c):
        pass
      elif c.isspace():
        attribute_name = content[attribute_name_start:pos]
        state = TAG_ATTRIBUTE_SPACE
      elif c == '/':
        tag_attributes.append(TagAttribute(content[attribute_name_start:pos]))
        state = TAG_AUTOCLOSE
      elif c == '>':
        tag_attributes.append(TagAttribute(content[attribute_name_start:pos]))
        yield TagOpen(tag_name, tag_attributes)
        state = START
        text_start = pos + 1
        text_chunks = []
      elif c == '=':
        attribute_name = content[attribute_name_start:pos]
        state = TAG_ATTRIBUTE_EQUALS
      else:
        raise Exception("Unknown char after attribute name: '%s' (%s)" % (c, position))
    elif state == TAG_ATTRIBUTE_SPACE:
      if isAttributeNameChar(c):
        tag_attributes.append(TagAttribute(attribute_name))
        attribute_name_start = pos
        attribute_name = ''
        state = TAG_ATTRIBUTE
      elif c.isspace():
        pass
      elif c == '/':
        tag_attributes.append(TagAttribute(attribute_name))
        state = TAG_AUTOCLOSE
      elif c == '=':
        state = TAG_ATTRIBUTE_EQUALS
      elif c == '>':
        tag_attributes.append(TagAttribute(attribute_name))
        yield TagOpen(tag_name, tag_attributes)
        state = START
        text_start = pos + 1
        text_chunks = []
      else:
        raise Exception("Unknown char after attribute name: '%s' (%s)" % (c, position))
    elif state == TAG_ATTRIBUTE_EQUALS:
      if c.isalpha():
        attribute_value_start = pos
        attribute_value = ''
        attribute_value_end = ' /'
        state = TAG_ATTRIBUTE_EQUALS_VALUE
      elif c == '"':
        attribute_value_start = pos
        attribute_value = ''
        attribute_value_end = '"'
        state = TAG_ATTRIBUTE_EQUALS_VALUE
      elif c == "'":
        attribute_value_start = pos
        attribute_value = ''
        attribute_value_end = "'"
        state = TAG_ATTRIBUTE_EQUALS_VALUE
      elif c.isspace():
        pass
      else:
        raise Exception("Unknown char after attribute '=': '%s' (%s)" % (c, position))
    elif state == TAG_ATTRIBUTE_EQUALS_VALUE:
      if c in attribute_value_end:
        if ' ' in attribute_value_end:
          end = pos
        else:
          end = pos + 1
        attribute_value = content[attribute_value_start:end]
        tag_attributes.append(TagAttribute(attribute_name, attribute_value))
        if c == '/':
          state = TAG_AUTOCLOSE
        else:
          state = TAG_INNER
    elif state == TAG_AUTOCLOSE:
      if c == '>':
        yield TagOpenClose(tag_name, tag_attributes)
        state = START
        text_start = pos + 1
        text_chunks = []
      else:
        raise Exception("Expected '>' after '/', but got: '%s' (%s)" % (c, position))
    elif state == TAG_CLOSE:
      if c.isalpha():
        tag_name_start = pos
        state = TAG_CLOSE_NAME
      else:
        raise Exception("Expected tag name after '</', but got: '%s' (%s)" % (c, position))
    elif state == TAG_CLOSE_NAME:
      if c.isalpha():
        pass
      elif c == '>':
        yield TagClose(content[tag_name_start:pos])
        state = START
        text_start = pos + 1
        text_chunks = []
    elif state == SPECIAL_TAG:
      if c == '>':
        yield SpecialTag(content[special_tag_start:pos + 1])
        state = START
        text_start = pos + 1
        text_chunks = []
      elif c == '"' or c == "'":
        state = SPECIAL_TAG_STRING
        special_tag_string_ending = c
    elif state == SPECIAL_TAG_STRING:
      if c == special_tag_string_ending:
        state = SPECIAL_TAG
    position.processChar(c)
  assert state == START
  yield content[text_start:]

def main(argv):
  if len(argv) != 1:
    print('Usage:\n    svg.py input-file')
    sys.exit(1)
  with open(argv[0], 'r') as f:
    contents = f.read()
  ast = parseTags(contents)
  print(ast)

if __name__ == '__main__':
    main(sys.argv[1:])
