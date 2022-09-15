#!/usr/bin/env python3
import os
from posixpath import basename
import logging as log
import re
import stat
import xml.etree.ElementTree as ET
import argparse
import sys

def appendToFile(file, categoryNameCorrected, categoryNameRegex, keywordString):
    try:
        print("  aws macie2 create-custom-data-identifier --name \"" + categoryNameCorrected.replace(" ", "")+ "\" --regex \"" + categoryNameRegex +  "\" --client-token $token --keywords ", keywordString, file=file)
    except Exception as e:
        log.error(e)
        sys.exit(1)

def bashHeader(args, file):
    file.write('''#!/usr/bin/env bash

set -Eeuo pipefail
trap cleanup SIGINT SIGTERM ERR EXIT

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)

usage() {
  cat << EOF # remove the space between << and EOF, this is due to web plugin issue
Usage: $(basename "${BASH_SOURCE[0]}") [-h] [-i file] token

This script was generated to create custom data identifiers on AWS 
using macie2. It requires the use of the AWS Security Token Service.
Read the AWS CLI documentation on how to generate a session token.
https://docs.aws.amazon.com/cli/latest/reference/sts/get-session-token.html#examples
        
Requirements:
token           This is your AWS Session Token

Available options:

-h, --help      Print this help and exit
-i, --include   You can optionally include custom data identifiers.

The custom data identifier file should be a list of regex search
strings and up to 50 associated keywords. Each custom data 
identifier should have the following format:
        <name>~<regex_string>~keyword~keyword~...~lastKeyword
For Example:
      name~\b(?:Word1|Word2)\b~associatedKeyword~associatedkeyword

EOF
  exit
}

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
  set -o history
}

setup_colors() {
  if [[ -t 2 ]] && [[ -z "${NO_COLOR-}" ]] && [[ "${TERM-}" != "dumb" ]]; then
    NOFORMAT='\\033[0m' RED='\\033[0;31m' GREEN='\\033[0;32m' ORANGE='\\033[0;33m' BLUE='\\033[0;34m' PURPLE='\\033[0;35m' CYAN='\\033[0;36m' YELLOW='\\033[1;33m'
  else
    NOFORMAT='' RED='' GREEN='' ORANGE='' BLUE='' PURPLE='' CYAN='' YELLOW=''
  fi
}

msg() {
  echo >&2 -e "${1-}"
}

die() {
  local msg=$1
  local code=${2-1} # default exit status 1
  msg "$msg"
  exit "$code"
}

parse_params() {
  # default values of variables set from params
  flag=0
  input=''
  
  while :; do
    case "${1-}" in
    -h | --help) usage ;;
    --no-color) NO_COLOR=1 ;;
    -i | --input)
      input="${2-}"
      shift
      ;;
    -?*) die "Unknown option: $1" ;;
    *) break ;;
    esac
    shift
  done

  args=("$@")

  # check required params and arguments
  [[ ${#args[@]} -eq 0 ]] && die "Missing script arguments"

  return 0
}

run_generated() {
  args=("$@")
  if [[ ${#args[@]} -eq 3 ]]; then
    token="${args[2]}"
  else
    token="$args"
  fi
''')
    
def bashFooter(args, file):
    file.write('''}

run_supplied(){
  args=("$@")
  if [[ ${#args[@]} -eq 3 ]]; then
    while IFS="" read -r p || [ -n "$p" ]
    do
      export IFS="~"
      counter=1
      name=""
      regex=""
      keywords=""
      for word in $p; do
        if [ "${counter}" == "1" ]; then
          name+='"'
          name+="$word"
          name+='"'
        elif [ "${counter}" == "2" ]; then
          regex+='"'
          regex+="$word"
          regex+='"'
        else
          keywords+='"'
          keywords+="$word"
          keywords+='" '
        fi
        counter=$((counter +1))
      done
      supplied_command="aws macie2 create-custom-data-identifier --name $name --regex $regex --token $3 --keywords $keywords"
      echo "Running: \'$supplied_command\'"
      eval $supplied_command
    done < ${args[1]}
    
  fi
}

set +o history
parse_params "$@"
setup_colors
run_supplied "$@"
run_generated "$@"
set -o history

msg "${RED}Read parameters:${NOFORMAT}"
msg "- flag: ${flag}"
msg "- param: ${param}"
msg "- arguments: ${args[*]-}"''')
def camelCase(s):
  s = re.sub(r"(_|-)+", " ", s).title().replace(" ", "")
  return ''.join([s[0].lower(), s[1:]])

def cmdline_args():
        # Make parser object
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    p.add_argument("inputFile", help="The XML Data File")
    p.add_argument("-v", "--verbose", action="store_true", help="Output debugging information")
    return(p.parse_args())

def parseXML(args, file):
    tree = ET.parse(args.inputFile)
    log.info("%s", tree.parse)
    
    root = tree.getroot()
    log.info("Root Node: %s", root.tag)

    for taxonomy in root.findall('taxonomy'):
        taxonomyName=taxonomy.find('name').text                                                 # taxonomyName
        log.info("\n\nTaxonomy Node: %s",taxonomyName)
        #for classes in taxonomy.findall('classes'):
        for category in taxonomy.findall('.//class'):
            categoryName=category.find('name').text     
            categoryNameRegex=regexCrafter(categoryName)# categoryName
            log.info("Category: %s",categoryName)
            keywords=list()
            regexlist=list()
            for clue in category.findall('.//classclue'):
                clueParts = dict()                                                      # clueParts Dict
                clueParts.update({"id":int(clue.find('clueid').text)})                  # id
                clueParts.update({"type":int(clue.find('type').text)})                  # type
                clueParts.update({"name":clue.find('clue').text})                      # name
                clueParts.update({"parentID":None})                                    # name
                match int(clue.find('type').text):     
                    case 1: # Standard
                        log.info("Standard Clue: %s",clueParts.get("name"))
                        keywords.append(clueParts.get("name"))
                        continue
                    case 4: # FILETYPE
                        log.info("Filetype Regex Clue: %s",clueParts.get("name"))
                        continue
                    case 5: # Phonetic
                        log.info("Phonetic Clue: %s",clueParts.get("name"))
                        keywords.append(clueParts.get("name"))
                        continue
                    case 6: # Regex Term
                        log.info("Regex Clue: %s",clueParts.get("name"))    
                        
                        regexlist.append(clueParts.get("name"))    
                        continue                        
                    case 13: # Heirarchical Term - Parent
                        clueParts.update({"name": clue.find('reference').text})
                        index = clue.find('clue').text.find('|') + 1
                        clueParts.update({"parentID": clue.find('clue').text[index:]})
                        log.info("Heirarchical Clue: %s", clueParts.get("name"))
                        continue
                    case _: # Unrecognized Term Type
                        log.warning("Unknown Clue: %s\tType: %s",clueParts.get("name"),clueParts.get("type"))
                        keywords.append(clueParts.get("name"))
                        continue
                    
            keywordString = ''
            categoryName = ''.join([taxonomyName,"_",categoryName])
            categoryNameCorrected=camelCase(re.sub(r"[^a-zA-Z0-9 _]", "", categoryName))
            for keyword in keywords:
                keywordString = r''.join([keywordString,'"',re.sub(r"[^a-zA-Z0-9 ]", "", keyword),'" '])
            keywordString=keywordString[:-1]
            appendToFile(file, categoryNameCorrected, categoryNameRegex, keywordString)
            while(len(regexlist) > 0):
                appendToFile(file, ''.join([categoryNameCorrected,str(len(regexlist))]), regexlist.pop(), keywordString)
            

def regexCrafter(term):
    categoryNameRegex=r"\b(?:"
    try:
        for word in term.split():
            categoryNameRegex=r''.join([categoryNameRegex,word,'|'])
    except Exception as e:
        pass
    categoryNameRegex=categoryNameRegex[:-1]
    categoryNameRegex=r''.join([categoryNameRegex,r")\b"])
    return categoryNameRegex
            
if __name__ == '__main__':
    try:
        args = cmdline_args()
        if args.verbose:
            log.basicConfig(format="%(levelname)s: %(message)s", level=log.DEBUG)
            log.info(args)
            file = open("awsMacieCustomDataIdentifiers.sh","w+")
            file.truncate(0)
            file.close()   
    except Exception as e:
        log.critical(e, exec_info=True)
        sys.exit(2)
    
    file = open("awsMacieCustomDataIdentifiers.sh", 'a+')
    bashHeader(args, file)
    parseXML(args, file)
    bashFooter(args, file)
    file.close()
    st = os.stat('awsMacieCustomDataIdentifiers.sh')
    os.chmod('awsMacieCustomDataIdentifiers.sh', st.st_mode | stat.S_IEXEC)