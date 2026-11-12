from rich import print


def pprint(created: list, updated: list, up_to_date: list, errors: list, nb_tabs: int):
    """Pretty print information on the current sync

    Args:
        created (list): Objects created through Playbook API
        updated (list): Objects updated
        up_to_date (list): Objects that were already up-to-date
        errors (list): Errors encountered during sync
        nb_tabs (int): Cue for vertical alignment
    """
    tab = "\t"
    if created:
        print(f"[green]{tab * nb_tabs}Created: {', '.join(created)}[/green]")
    if updated:
        print(f"[green]{tab * nb_tabs}Updated: {', '.join(updated)}[/green]")
    if up_to_date:
        print(
            f"[green]{tab * nb_tabs}Already Up-To-Date: \
{', '.join(up_to_date)}[/green]"
        )
    if errors:
        err: str = "Error" if len(errors) == 1 else "Errors"
        print(f"[red]{tab * nb_tabs}{err}: {', '.join(errors)}[/red]")
