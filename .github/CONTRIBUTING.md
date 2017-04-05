# Contribution guidelines

Thanks for helping out!  :relaxed:  Here's a few pointers to ease the back-and-forth with contributions.

## Before submitting

- If you have a question, please check the documentation, as well as previously raised issues, to see if it's already been answered.
- Check out the latest version of the code, in case the bug you want to report has already been fixed.
- Make sure you're not encountering a server-side issue, particularly with authentication.  Try logging into [Skype for Web](https://web.skype.com) to see where the problem lies.

## Creating an issue

- The issue form comes with a template that covers the basics -- please fill in all parts as appropriate.
- You'll need a suitable snippet of output (including HTTP debugging if related to the Skype API itself) and steps to reproduce the problem.

## Creating a pull request

- Maintain the code style (effectively PEP-8, but with a maximum line width of 120 characters, and consistent choices for line breaks).
- If adding new methods or classes, include suitable docstrings with argument and return types.
- Make sure your code works on both Python 2.6 and 3.x.  Unit tests are included to run some basic checks.
