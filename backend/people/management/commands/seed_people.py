from django.core.management.base import BaseCommand

from people.models import Person

# Startowa baza referencyjna: osoby publiczne, których wizerunek bywa nadużywany w fałszywych reklamach.
# Rozpoznawanie działa po wzmiance w tekście (z odmianą). Rozmiar bazy nie ma znaczenia, listę łatwo rozszerzyć.
PEOPLE = [
    "Rafał Brzoska", "Monika Olejnik", "Krzysztof Stanowski", "Tomasz Sekielski", "Mateusz Morawiecki", "Donald Tusk",
    "Andrzej Duda", "Karol Nawrocki", "Rafał Trzaskowski", "Sławomir Mentzen", "Szymon Hołownia", "Radosław Sikorski",
    "Adam Glapiński", "Andrzej Domański", "Robert Lewandowski", "Anna Lewandowska", "Iga Świątek", "Zbigniew Boniek",
    "Kuba Wojewódzki", "Martyna Wojciechowska", "Ewa Drzyzga", "Piotr Kraśko", "Krzysztof Ibisz", "Katarzyna Dowbor",
    "Jerzy Owsiak", "Dominika Kulczyk", "Sebastian Kulczyk", "Michał Sołowow", "Daniel Obajtek", "Elon Musk",
]


class Command(BaseCommand):
    help = "Zakłada startową bazę referencyjną osób publicznych."

    def handle(self, *args, **options):
        created = sum(Person.objects.get_or_create(name=name)[1] for name in PEOPLE)
        self.stdout.write(self.style.SUCCESS(f"Osoby w bazie: {Person.objects.count()} (nowych: {created})"))
