# -*- coding: utf-8 -*-

import os
import re
from bs4 import formatter, BeautifulSoup as bs

xml_4indent_formatter = formatter.XMLFormatter(indent=4)

def get_files_recursive(path):
    xml_files = []
    for item in os.listdir(path):
        if os.path.isfile(os.path.join(path, item)) and item.endswith('.xml'):
            xml_files.append(os.path.join(path, item))
        if os.path.isdir(os.path.join(path, item)):
            xml_files.extend(get_files_recursive(os.path.join(path, item)))
    return xml_files

root_dir = input('Enter root directory to check (empty for current directory) : ')
root_dir = root_dir or '.'
all_xml_files = get_files_recursive(root_dir)

def normalize_domain(domain):
    """Normalize Domain, taken from odoo/osv/expression.py -> just the part so that & operators are added where needed.
        After that, we can use a part of the def parse() from the same file to manage parenthesis for and/or"""
    if len(domain) == 1:
        return domain
    result = []
    expected = 1                            # expected number of expressions
    op_arity = {'!': 1, '&': 2, '|': 2}
    for token in domain:
        if expected == 0:                   # more than expected, like in [A, B]
            result[0:0] = ['&']             # put an extra '&' in front
            expected = 1
        if isinstance(token, (list, tuple)):  # domain term
            expected -= 1
            token = tuple(token)
        else:
            expected += op_arity.get(token, 0) - 1
        result.append(token)
    return result

def stringify_leaf(leaf):
    stringify = ''
    switcher = False
    # Replace operators not supported in python (=, like, ilike)
    operator = str(leaf[1])
    if operator == '=':
        operator = '=='
    elif 'like' in operator:
        if 'not' in operator:
            operator = 'not in'
        else:
            operator = 'in'
        switcher = True
    # Take left operand, never to add quotes (should be python object / field)
    left_operand = leaf[0]
    # Take care of right operand, don't add quotes if it's list/tuple/set/boolean/number, check if we have a true/false/1/0 string tho.
    right_operand = leaf[2]
    if right_operand in ('True', 'False', '1', '0') or type(right_operand) in (list, tuple, set, int, float, bool):
        right_operand = str(right_operand)
    else:
        right_operand = "'"+right_operand+"'"
    stringify = "%s %s %s" % (right_operand if switcher else left_operand, operator, left_operand if switcher else right_operand)
    return stringify

def stringify_attr(stack):
    if stack in (True, False, 'True', 'False', 1, 0, '1', '0'):
        return stack
    last_parenthesis_index = max(index for index, item in enumerate(stack[::-1]) if item not in ('|', '!'))
    stack = normalize_domain(stack)
    stack = stack[::-1]
    result = []
    for index, leaf_or_operator in enumerate(stack):
        if leaf_or_operator == '!':
            expr = result.pop()
            result.append('(not (%s))' % expr)
        elif leaf_or_operator == '&' or leaf_or_operator == '|':
            left = result.pop()
            right = result.pop()
            form = '(%s %s %s)'
            if index > last_parenthesis_index:
                form = '%s %s %s'
            result.append(form % (left, 'and' if leaf_or_operator=='&' else 'or', right))
        else:
            result.append(stringify_leaf(leaf_or_operator))
    result = result[0]
    return result

def get_new_attrs(attrs):
    new_attrs = {}
    attrs_dict = eval(attrs.strip())
    for attr in {'required', 'invisible', 'readonly'}:
        if attr in attrs_dict.keys():
            new_attrs[attr] = stringify_attr(attrs_dict[attr])
    return new_attrs

# Prettify puts <attribute> on three lines (1/ opening tag, 2/ text, 3/ closing tag), not very cool.
# Taken from https://stackoverflow.com/questions/55962146/remove-line-breaks-and-spaces-around-span-elements-with-python-regex
# And changed to avoid putting ALL one line, and only manage <attribute>, as it's the only one messing stuff here
# Kinda ugly to use the 3 types of tags but tbh I keep it like this while I have no time for a regex replace keeping the name="x" :p
def prettify_output(html):
    for attr in {'required', 'invisible', 'readonly'}:
        html = re.sub(f'<attribute name="{attr}">[ \n]+',f'<attribute name="{attr}">', html)
    html = re.sub(f'[ \n]+</attribute>',f'</attribute>', html)
    return html

autoreplace = input('Do you want to auto-replace attributes ? (y/n) (empty == no) (will not ask confirmation for each file) : ') or 'n'
nofilesfound = True
for xml_file in all_xml_files:
    with open(xml_file, 'rb') as f:
        contents = f.read().decode('utf-8')
        f.close()
        if not 'attrs' in contents:
            continue
        soup = bs(contents, 'xml')
        tags_with_attrs = soup.select('[attrs]')
        attribute_tags_name_attrs = soup.select('attribute[name="attrs"]')
        if not tags_with_attrs and not attribute_tags_name_attrs:
            continue
        nofilesfound = False
        print('Taking Care of XML File : %s' % xml_file)
        print(tags_with_attrs, attribute_tags_name_attrs)
        print('Will be replaced by')
        for tag in tags_with_attrs:
            attrs = tag['attrs']
            new_attrs = get_new_attrs(attrs)
            del tag['attrs']
            for new_attr in new_attrs.keys():
                tag[new_attr] = new_attrs[new_attr]
        attribute_tags_after = []
        for attribute_tag in attribute_tags_name_attrs:
            new_attrs = get_new_attrs(attribute_tag.text)
            for new_attr in new_attrs.keys():
                new_tag = soup.new_tag('attribute')
                new_tag['name'] = new_attr
                new_tag.append(str(new_attrs[new_attr]))
                attribute_tags_after.append(new_tag)
                attribute_tag.insert_after(new_tag)
            attribute_tag.decompose()
        print(tags_with_attrs, attribute_tags_after)
        if autoreplace.lower()[0] == 'n':
            confirm = input('Do you want to replace? (y/n) (empty == no) : ') or 'n'
        else:
            confirm = 'y'
        if confirm.lower()[0] == 'y':
            with open(xml_file, 'wb') as rf:
                html = soup.prettify(formatter=xml_4indent_formatter)
                html = prettify_output(html)
                rf.write(html.encode('utf-8'))
                rf.close()

if nofilesfound:
    print('No XML Files with "attrs" found in dir " %s "' % root_dir)
