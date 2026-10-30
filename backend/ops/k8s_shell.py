import shlex


BASH_INIT = r'''
if [ -r "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc"
fi
if ! declare -F _init_completion >/dev/null; then
    if [ -r /usr/share/bash-completion/bash_completion ]; then
        source /usr/share/bash-completion/bash_completion
    elif [ -r /etc/bash_completion ]; then
        source /etc/bash_completion
    fi
fi
if command -v kubectl >/dev/null 2>&1 && ! complete -p kubectl >/dev/null 2>&1; then
    source <(kubectl completion bash 2>/dev/null)
fi
bind '"\t": complete'
bind 'set show-all-if-ambiguous on'
'''


def interactive_shell_command(shell):
    if shell == 'auto':
        bash_command = shlex.join(interactive_shell_command('/bin/bash'))
        return ['/bin/sh', '-c', f'if [ -x /bin/bash ]; then exec {bash_command}; else exec /bin/sh -i; fi']
    if shell.rsplit('/', 1)[-1] == 'bash':
        startup = f'exec "$BASH" --noprofile --rcfile <(printf "%s\\n" {shlex.quote(BASH_INIT)}) -i'
        return [shell, '-c', startup]
    return [shell, '-i']
