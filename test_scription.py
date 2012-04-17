from scription import Script, Command, run

@Script()
def main(jobstep, blah='foo', **stuff):
    "testing cmd_line..."
    print jobstep, blah, stuff

if __name__ == '__main__':
    run()
