"""CLI for the Aquavena SDK."""

import sys

from rich.console import Console
from rich.table import Table
from rich import box

from .scraper import AquavenaClient

console = Console(width=220)


def _cmd_list() -> None:
    with AquavenaClient() as client:
        regimes = client.list_regimes()

    if not regimes:
        console.print("[red]Aucun régime trouvé.[/red]")
        return

    table = Table(title="Régimes Aquavena", box=box.ROUNDED, show_lines=True)
    table.add_column("Régime", style="bold cyan", no_wrap=True)
    table.add_column("Slug", style="dim")
    table.add_column("Description")
    table.add_column("Image URL", style="dim", overflow="fold")

    for r in regimes:
        table.add_row(r.name, r.slug, r.description, r.image_url)

    console.print(table)


def _cmd_menus(slug: str) -> None:
    with AquavenaClient() as client:
        menu = client.get_menus(slug)

    if not menu.days:
        console.print(f"[red]Aucun menu trouvé pour '{slug}'.[/red]")
        return

    if menu.description:
        from rich.panel import Panel
        console.print(Panel(menu.description, title=f"[bold cyan]{slug}[/bold cyan]", expand=False))

    table = Table(
        title=f"Menus — {slug}",
        box=box.ROUNDED,
        show_lines=True,
        expand=True,
    )
    table.add_column("Date",        style="bold cyan",  no_wrap=True, min_width=10)
    table.add_column("Formule",     style="dim",        no_wrap=True, min_width=7)
    table.add_column("Service",     style="bold",       no_wrap=True, min_width=14)
    table.add_column("Plat",        overflow="fold",    min_width=60)
    table.add_column("Suppléments", style="green dim",  overflow="fold", min_width=25)

    # Collect boissons for footer (usually identical every day)
    all_boissons: list[str] = []

    for day in menu.days:
        if not all_boissons and day.boissons:
            all_boissons = day.boissons
        suppl_text = "\n".join(day.supplements) or "—"

        services: list[tuple[str, str]] = []
        for d in day.midi():
            services.append(("[green]Midi[/green]", d.description))
        for d in day.soir():
            services.append(("[magenta]Soir[/magenta]", d.description))
        for d in day.gourmet():
            label = "Midi" if "midi" in d.meal_time.value else "Soir"
            services.append((f"[yellow]★ Gourmet {label}[/yellow]", d.description))
        if not services:
            services.append(("—", "—"))

        for i, (service, plat) in enumerate(services):
            table.add_row(
                day.date,
                day.formule if i == 0 else "",
                service,
                plat,
                suppl_text  if i == 0 else "",
            )

    console.print(table)
    console.print(f"[dim]{len(menu.days)} jour(s) — formule [bold]{menu.days[0].formule}[/bold][/dim]")
    if all_boissons:
        bois_table = Table(title="Boissons disponibles", box=box.SIMPLE, show_header=False)
        bois_table.add_column(style="blue dim", overflow="fold")
        for b in all_boissons:
            bois_table.add_row(f"· {b}")
        console.print(bois_table)


def _cmd_tarifs() -> None:
    with AquavenaClient() as client:
        tarifs = client.get_tarifs()

    if not tarifs:
        console.print("[red]Aucun tarif trouvé.[/red]")
        return

    for rt in tarifs:
        table = Table(
            title=rt.regime,
            box=box.ROUNDED,
            show_lines=True,
        )
        table.add_column("Formule / Article", overflow="fold", min_width=50)
        table.add_column("Prix HT (XPF)",  style="dim",        no_wrap=True, justify="right")
        table.add_column("Prix TTC (XPF)", style="bold green", no_wrap=True, justify="right")

        for item in rt.items:
            table.add_row(
                item.label,
                f"{item.price_ht:,}".replace(",", " "),
                f"{item.price_ttc:,}".replace(",", " "),
            )
        console.print(table)
        console.print()


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "list":
        _cmd_list()
    elif args[0] == "menus" and len(args) >= 2:
        _cmd_menus(args[1])
    elif args[0] == "tarifs":
        _cmd_tarifs()
    else:
        console.print("[bold]Usage :[/bold]")
        console.print("  aquavena list                — lister les régimes")
        console.print("  aquavena menus <slug>        — menus d'un régime")
        console.print("  aquavena tarifs              — grille tarifaire")
        sys.exit(1)


if __name__ == "__main__":
    main()
