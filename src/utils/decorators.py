import inspect
import re
import time

from constants.constants import INDENT_2_TABS
from utils.colorise import Colorise
from common.globals import COUNTERS


def print_current_task_name(fn):
    def wrapper(*args, **kwargs):
        COUNTERS["TASKS"] += 1
        print_function_name(inspect.stack()[1][4][0], COUNTERS["TASKS"])
        result = fn(*args, **kwargs)
        return result
    return wrapper


def print_function_name(raw_stack_name, task_counter):
    verify_if_function_is_a_task(raw_stack_name)
    fn_name = raw_stack_name.replace('_TASK_', '').strip()
    fn_name = fn_name.split(" = ")[1] if " = " in fn_name else fn_name
    fn_name = fn_name.replace('_', ' ')
    fn_name = re.sub(r'\([^()]*\)', '', fn_name)
    fn_name = fn_name[0].upper() + fn_name[1:]
    fn_name = fn_name.ljust(38, ' ')  # Fill the string with "_" characters
    fn_name2 = f"########  TASK {str(task_counter).rjust(2, ' ')}:  {fn_name}  {'#' * 44}"
    print((Colorise.green(fn_name2)))


def verify_if_function_is_a_task(raw_stack_name):
    if not "_TASK_" in raw_stack_name:
        error_message = f"Error: function name does not contain '_TASK_': {raw_stack_name} - remove 'print_function_name' decorator."
        print((Colorise.red(error_message)))
        exit(1)


def display_timing(fn):
    """Outputs the time a function takes to execute."""

    def wrapper(*args, **kwargs):
        t = time.time()
        result = fn(*args, **kwargs)
        t_diff = time.time() - t
        if t_diff >= 0.01:
            print((Colorise.yellow(INDENT_2_TABS + "    Execution time: ") +
                   str(round(t_diff, 2)) + Colorise.yellow(" s")))
        return result
    return wrapper
