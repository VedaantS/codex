# codex

## Setup

### Cloning

The first step to getting this repo is to clone it by running `git clone https://github.com/VedaantS/codex.git` on a new terminal window. If that does not work, on the homepage of this project [here](https://github.com/VedaantS/codex), click Code -> Download ZIP. Let the ZIP download and open it up. 

If you downlaoded a ZIP, open up a new terminal window, and run `cd ~/downloads/codex` in that window. If you cloned it through `git clone`, just `cd ~/codex` should do. 

*(PS: You execute a terminal command by going into the terminal app, typing into the space provided, and clicking enter.)*

### Homebrew

First, install Homebrew. 

You can check whether you have it by using your terminal window (with the `cd` commands executed). and saying `brew --version`. 

If you get an output like `zsh: command not found: brew`, then you know you need to install Homebrew. Do so by running the command `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` in terminal and follow any relevant instructions (if applicable). 

If you get an output like `Homebrew 4.5.3`, ignore this step and move on. 


### Postgres

Our databasing system uses PostgreSQL, an industry-standard databasing system (along with MySQL/MariaDB or MongoDB). 

To see whether you have Postgres, run the command `psql`. 

If that returns a `command not found` interface, download PostgreSQL by typing into terminal `brew install postgresql`, and follow any relevant instructions (if applicable).

Then, run these commands in your terminal (or inside `psql` as a superuser like `postgres`):

```sql
-- Connect as a superuser, e.g. psql -U postgres
CREATE USER jaivirsingh WITH PASSWORD 'my_password';
CREATE DATABASE jaivirsingh OWNER jaivirsingh;
```
---

Use `psql` to load the schema file into the new database:

```bash
psql -U jaivirsingh -d jaivirsingh -f schema_export.sql
```

* This connects as user `jaivirsingh` to database `jaivirsingh`
* Runs all the commands from `schema_export.sql` to create your schema

---
Go into the file `codex_api.py`. Replace `vedaantsrivastava` with `jaivirsingh`, and `my_password` with whatever your real password is (unless you set your db password as `my_passowrd`; that's what I did). 

Postgres is then set up and capable of storing data. 

### Python/Flask

Our server runs on flask, a minimalistic Python server system. It can currently only concurrently handle 200-300 users; before deployment, minimal changes will allow us to tie it to Gunicorn or Celery, which are frameworks built on top of Flask that can scale far more easily. 

I assume, since you have a new computer, you have Python installed by default. You can check this by running `python3 --version` on your computer. A 'command not found' error means you do *not* have it currently installed; you should install `brew install python@3.13` in this scenario, and follow any relevant instructions (if applicable). 

Once Python is installed, run the following command in your terminal:

`pip3 install -r requirements.txt`.

When all packages are installed, run `python3 codex_api.py`.

You should now navigate to `http://localhost:5000` on any browser window, and Codex should work as expected. 

### Editing

To edit or refine code, install <a href="https://code.visualstudio.com/">Visual Studio Code</a>, and, when prompted, follow all setup instructions. Then, when it is set up, open a new window and click 'Open'. From there, open the folder in which the code is. Changes to either HTML files or the Python server should sync in real-time. You can additionally use Copilot in Agent mode to help sync these changes for you. 

To save a change to the GitHub project (as opposed to just on your own computer), run the following command:

`git add .; git commit -m 'jaivir update'; git push;`.

This will save all your changes made locally to the main git repo.
