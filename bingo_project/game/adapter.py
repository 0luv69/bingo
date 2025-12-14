from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from allauth.exceptions import ImmediateHttpResponse

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        print("Running CustomSocialAccountAdapter...")  # Debug line
        print("SOCIAL LOGIN EMAIL:", sociallogin.account.extra_data.get("email"))

# class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
#     def pre_social_login(self, request, sociallogin):
#         """
#         Check for email conflicts during social login and redirect to a custom conflict-resolver page.
#         """
#         email = sociallogin.account.extra_data.get("email", None)

#         # If no email is provided, skip further checks
#         if not email:
#             return

#         try:
#             # Check if a user with this email already exists
#             existing_user = User.objects.get(email=email)

#             # Redirect if the email belongs to another provider (e.g., Google)
#             if existing_user.socialaccount_set.exists():
#                 provider = existing_user.socialaccount_set.first().provider

#                 # Store extra session info for the template and user experience
#                 request.session["merge_conflict_email"] = email
#                 request.session["merge_conflict_provider"] = provider

#                 # Redirect user to the custom conflict resolution page
#                 raise ImmediateHttpResponse(redirect("/merge-account/"))

#         except User.DoesNotExist:
#             pass  # Continue with Allauth's default behavior if no conflict exists