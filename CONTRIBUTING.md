# Contributing to the project
First of all, thanks for taking the time to improve the project!

## Code contribution
Here's a basic guide on how to contribute code. Make sure you have good knowledge of Python, discord.py and git.
1. Fork the project on the GitHub website. 
2. Clone the fork using `git clone <URL>` on a clean directory.
    - Depending on how you set up git, you may need to use the SSH address. If your git authentication is SSH key-based, then clone using the SSH address. Otherwise,
    you can clone using the HTTPS address.
3. Make your changes, add files to the commit using `git add -A` or `git add file1 file2 ...` for specific files. Then, commit and push to the remote.
4. Submit a pull request on the main GitHub repository.

Familiarize yourself with the architecture of the codebase before starting to make changes.

Before committing changes, ensure your fork has a .gitignore file and **_that there's a .env entry in it_** to exclude the .env file containing **your bot's token**. Check with `git status` or by using an IDE with git integration.

## Bug reports
To contribute bug reports, you can easily submit one thanks to the dedicated GitHub issue template.

Please refrain from submitting vague "doesn't work" bug reports. Giving basic information as a heads-up greatly improves the speed of triaging the issue.