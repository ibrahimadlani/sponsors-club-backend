# Database seeding

Use the `seed` management command to populate a demo dataset that covers users, organisations, athletes, and analytics records. This is ideal for showcasing the API and the proof-of-concept templates bundled with the project.

## Prerequisites
1. Apply all migrations (`python manage.py migrate`). The payments app ships a data migration (`0003_seed_subscription_plans.py`) that inserts required subscription plans referenced by tests and entitlements.
2. Ensure the Faker library is installed. It is pinned in `requirements.txt`, so `pip install -r requirements.dev.txt` already satisfies this dependency.

## Running the command
```bash
python manage.py seed
```
The command wraps all inserts in a single transaction. If anything fails, no partial data remains in the database.

### Available options
| Option | Default | Description |
| ------ | ------- | ----------- |
| `--agents` | `5` | Number of agent users (with attached `AgentProfile`) to create. |
| `--organisations` | `5` | Number of organisations and collaborator owners to generate. |
| `--sports` | `6` | Number of sports available for athlete assignment. |
| `--athletes` | `15` | Number of athletes to create and link to agents/sports. |
| `--seed` | _none_ | Integer seed that produces deterministic Faker output and random selections. |

Example:
```bash
python manage.py seed --agents 3 --organisations 2 --athletes 10 --seed 42
```

## Generated records
- **Agents:** Each receives a unique email and profile bio. Credentials use the shared password `Passw0rd!`.
- **Organisations and collaborators:** Every organisation has an owner collaborator with a generated job title and company metadata.
- **Sports:** Populated with unique names and disciplines.
- **Athletes:** Linked to both sports and agents, with realistic dates of birth and nationality codes.
- **Analytics:** Each athlete gets daily statistics across multiple social platforms for the past 30 days.

## Resetting data
To return to a clean state, run:
```bash
python manage.py flush --noinput
python manage.py migrate
```
You can then re-run `python manage.py seed` to regenerate the demo dataset.
