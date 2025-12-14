from allauth. socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from allauth.account.models import EmailAddress


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to handle social account email conflicts.
    
    When a user tries to sign in with a social provider but their email
    already exists (from another provider), we redirect to a custom
    conflict resolution page instead of the default signup page.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Called after authentication, before the login is actually processed.
        
        This is where we detect email conflicts and redirect to our custom
        merge/conflict page.
        """
        # If the social account already exists and is connected, let it proceed
        if sociallogin. is_existing: 
            return

        # Check if there's an email associated with this social login
        email = sociallogin.user.email
        if not email:
            # Try to get email from extra_data
            extra_data = sociallogin.account.extra_data
            email = extra_data.get('email')

        if not email:
            return  # No email, can't check for conflicts

        # Check if this email already exists in the database
        try:
            existing_email = EmailAddress.objects. get(email__iexact=email)
            existing_user = existing_email.user

            # Store the sociallogin in session for later use
            # This is important - we need it when the user confirms the merge
            request.session['socialaccount_sociallogin'] = sociallogin.serialize()
            request.session['conflicting_user_id'] = existing_user.pk
            request.session['conflict_email'] = email
            
            # Get the existing provider(s) for this user
            existing_providers = list(
                existing_user.socialaccount_set.values_list('provider', flat=True)
            )
            request.session['existing_providers'] = existing_providers

            # Redirect to our custom conflict resolution page
            raise ImmediateHttpResponse(redirect('account_conflict'))

        except EmailAddress.DoesNotExist:
            # No conflict, proceed normally
            pass

    def authentication_error(
        self, request, provider_id, error=None, exception=None, extra_context=None
    ):
        """Handle authentication errors gracefully."""
        messages.error(
            request,
            f"There was an error signing in with {provider_id}.  Please try again."
        )
        return redirect('home')


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter for additional account handling.
    """
    
    def get_login_redirect_url(self, request):
        """Redirect to dashboard after login."""
        return '/'  # Change this to your desired redirect URL