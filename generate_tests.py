import logging
import os
import random
import shutil


DEFAULT_NUM_GROUPS = 7
DEFAULT_NUM_QUESTIONS_PER_GROUP = 5

QUESTIONS_DIR = 'all-questions'
QUESTION_END_MARKER = '.'

GENERATED_TESTS_DIR = 'generated-tests'
GENERATED_TEST_FILENAME_FMT = "%sG%d.txt"
GENERATED_TEST_HEADER_FMT = "//Pitanja za PJiSP %sG%d\n"
GENERATED_TEST_QUESTION_FMT = """*%d
/t
%s
"""


def list_files_in_dir(path):
    """"
    Return a list containing the names of the files in the directory, while
    ignoring hidden files and directories.
    """
    return filter(
        lambda x: x[0] != '.' and os.path.isfile(os.path.join(path, x)),
        os.listdir(path)
    )

def list_subdirs_in_dir(path):
    """"
    Return a list containing the names of the subdirectories in the directory,
    while ignoring hidden files and directories.
    """
    return filter(
        lambda x: x[0] != '.' and os.path.isdir(os.path.join(path, x)),
        os.listdir(path)
    )

# Based on `fabric.operations.prompt`
def prompt(text, default_value='', validate=None):
    default_str = " [%s] " % default_value if default_value else ''
    prompt_str = text + default_str
    
    value = None
    while value is None:
        value = raw_input(prompt_str) or default_value
        
        if callable(validate): 
            try:
                # Callable validate() must raise an exception if validation fails
                value = validate(value)
            except Exception, e:
                # Reset value so we stay in the loop
                value = None
                print 'Validation failed:', e.message
    
    return value

def validate_choice(choices, coerce=None):
    def validate(x):
        if callable(coerce):
            x = coerce(x)
        
        if x not in choices:
            raise ValueError("%s is not a valid choice" % x)
        return x
    
    return validate

def choose_test():
    choices = list_subdirs_in_dir(QUESTIONS_DIR)
    
    return prompt(
        text="Choose a test (%s): " % ', '.join(choices),
        validate=validate_choice(choices)
    )

def parse_question_file(test_id, filename):
    questions = []
    buff = []
    with open(os.path.join(QUESTIONS_DIR, test_id, filename), 'r') as fp:
        for line in fp:
                if line != '\n' or buff: # Skip the empty question header lines
                    buff.append(line)
                
                if line.strip() == QUESTION_END_MARKER:
                    questions.append(''.join(buff))
                    buff = []
                    logging.debug("Parsing %s, found question:\n%s", filename, questions[-1])
    
    logging.info("Parsed %s, found %d question(s)", filename, len(questions))
    return questions

def parse_questions(test_id):
    return dict(
        (filename, parse_question_file(test_id, filename))
        for filename in list_files_in_dir(os.path.join(QUESTIONS_DIR, test_id))
    )

def generate_tests(all_questions, test_id, num_groups, num_questions_per_group):
    num_questions_per_file = dict((f, len(q)) for f, q in all_questions.items())
    
    num_total_questions = sum(num_questions_per_file.values())
    num_questions_needed = num_groups * num_questions_per_group
    logging.info("Total %d question(s) found, need %d", num_total_questions, num_questions_needed)
    if num_questions_needed > num_total_questions:
        raise ValueError('Not enough questions found')
    
    def question_ids_to_str(question_ids):
        return ', '.join(sorted("%s:%d" % x for x in question_ids))
    
    available_question_ids = set([
        (filename, question_id)
        for filename, num_questions in num_questions_per_file.items()
            for question_id in range(num_questions) 
    ])
    for group_id in xrange(1, num_groups+1):
        logging.debug(
            "%d question(s) available for group %d: %s",
            len(available_question_ids), group_id, question_ids_to_str(available_question_ids)
        )
        while True:
            # Loop until all randomly chosen questions come from different question files
            chosen_question_ids = random.sample(available_question_ids, num_questions_per_group)
            filenames_used = set([filename for filename, _ in chosen_question_ids])
            if len(filenames_used) == num_questions_per_group:
                # The chosen questions are no longer available
                available_question_ids.difference_update(set(chosen_question_ids))
                break
            
        logging.info(
            "Chose the following question(s) for group %d: %s",
            group_id, question_ids_to_str(chosen_question_ids)
        )
        
        group_filename = GENERATED_TEST_FILENAME_FMT % (test_id, group_id)
        with open(os.path.join(GENERATED_TESTS_DIR, test_id, group_filename), 'w') as fp:
            fp.write(GENERATED_TEST_HEADER_FMT % (test_id, group_id))
            for idx, (filename, question_id) in enumerate(chosen_question_ids, start=1):
                fp.write(GENERATED_TEST_QUESTION_FMT % (
                    idx, all_questions[filename][question_id]
                ))
        
        logging.info("Generated the test %s for group %d", group_filename, group_id)

def main():
    # Setup command line option parser
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option(
        '-q',
        '--quiet',
        action='store_const',
        const=logging.WARN,
        dest='verbosity',
        help='Be quiet, show only warnings and errors'
    )
    parser.add_option(
        '-v',
        '--verbose',
        action='store_const',
        const=logging.DEBUG,
        dest='verbosity',
        help='Be very verbose, show debug information'
    )
    (options, _) = parser.parse_args()
    
    # Configure logging
    log_level = options.verbosity or logging.INFO
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")
    
    # Parse input
    test_id = choose_test()
    num_groups = prompt(
        text='How many student groups?',
        default_value=DEFAULT_NUM_GROUPS,
        validate=int
    )
    num_questions_per_group = prompt(
        text='How many questions per group?',
        default_value=DEFAULT_NUM_QUESTIONS_PER_GROUP,
        validate=int
    )
    
    # Sanity check, prompt before overwriting existing files
    generated_tests_dir = os.path.join(GENERATED_TESTS_DIR, test_id)
    if os.path.exists(generated_tests_dir):
        answer = prompt(
            text="Directory '%s' already exists, are you sure you want to delete it (Y/N)? " % generated_tests_dir,
            validate=validate_choice('YN')
        )
        if answer == 'N':
            exit()
        
        shutil.rmtree(generated_tests_dir)
    
    os.makedirs(generated_tests_dir)
    
    # Generate tests
    all_questions = parse_questions(test_id)
    generate_tests(all_questions, test_id, num_groups, num_questions_per_group)
    
    logging.info('DONE!')

if __name__ == '__main__':
    main()