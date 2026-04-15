class Employee:
    company = 'TechCorp'     


e1 = Employee()
e2 = Employee()

e1.company = 'InnoTech'  # This creates an instance variable for e1, not affecting the class variable
e1.rujal = 'Rujal'  # This creates an instance variable for e1

print(e1.rujal)  # Output: Rujal
print(repr(e1))  # Output: <__main__.Employee object at 0x...>
print(Employee.company)  # Output: TechCorp
print(e1.company)  # Output: InnoTech
print(e2.company)  # Output: TechCorp