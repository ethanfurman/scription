from scription import Script, Command, Run, InputFile

@Script(blah=('configuration file',None,None,InputFile))
def main(jobstep, blah='foo', **stuff):
    "testing cmd_line..."
    print jobstep, blah, stuff

if __name__ == '__main__':
    Run()
