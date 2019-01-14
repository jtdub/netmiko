class CommandBufferArbiter:
    """
    Acts as a send command rate limiter that maintains the “command buffer” at chunk_size number of commands.
    It would allow sending of chunk_size commands, when it sees X prompts come back, it allows another X command(s).
    If it doesn’t see a prompt come back in some time, it figures “I must have missed it” and sends another command.
    This continues until the config set is depleted.
    """

    def __init__(self, host, chunk_size=10, timeout=5, host_splice=16):
        self.host = host
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.host_splice = host_splice

        self.unacknowledged_commands = 0
        self.timer = None

        # lines that have already been checked for prompts
        self.completed_lines = []
        # lines that have yet to be checked for prompts
        self.pending_lines = []
        # The current line that has not yet been completed with a terminating EOL
        self.incomplete_line = ''

    def _line_has_prompt(self, line):
        if line.startswith(self.host[:self.host_splice]):
            return True
        return False

    def _count_prompts(self):
        count = 0
        while len(self.pending_lines):
            line = self.pending_lines.pop(0)
            if self._line_has_prompt(line):
                count += 1
            self.completed_lines.append(line)
        return count

    def _process_output(self, output):
        output_lines = output.splitlines()

        # If the output starts with a new line, close out the incomplete line
        if output.startswith('\n'):
            output_lines.insert(0, self.incomplete_line)
            self.incomplete_line = ''

        if output_lines:
            # Concatenate the incomplete line with the first line in the output
            output_lines[0] = self.incomplete_line + output_lines[0]
            self.incomplete_line = ''

            # Consider the last line incomplete if the output does not end with a new line
            if not output.endswith('\n'):
                self.incomplete_line = output_lines.pop()

        self.pending_lines.extend(output_lines)

    def how_many_more_commands_can_be_sent(self, output):
        import time

        self._process_output(output)
        number_or_prompts = self._count_prompts()

        # If we see at least one prompt, reset the timer, subtract from unacknowledged_commands
        if number_or_prompts:
            self.unacknowledged_commands -= min(number_or_prompts, self.unacknowledged_commands)
            self.timer = time.time()
        # If our timer has expired, acknowledge one command
        elif self.timer and time.time() - self.timer > self.timeout:
            if self.unacknowledged_commands:
                self.unacknowledged_commands -= 1
            self.timer = time.time()

        number_of_commands_to_send = self.chunk_size - self.unacknowledged_commands

        self.unacknowledged_commands += number_of_commands_to_send
        return number_of_commands_to_send

    def all_output(self):
        return "\n".join(
            self.completed_lines +
            self.pending_lines
        ) + self.incomplete_line
