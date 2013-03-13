from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _, ugettext_lazy

from newsletter_subscription.models import Subscription
from newsletter_subscription.signals import subscribed, unsubscribed
from newsletter_subscription.utils import (get_signer,
    send_subscription_mail, send_unsubscription_mail)


class NewsletterForm(forms.Form):
    email = forms.EmailField(label=ugettext_lazy('email address'),
        widget=forms.TextInput(attrs={
            'placeholder': ugettext_lazy('email address'),
            }), max_length=254)
    action = forms.ChoiceField(label=ugettext_lazy('action'), choices=(
        ('subscribe', _('subscribe')),
        ('unsubscribe', _('unsubscribe')),
        ), widget=forms.RadioSelect, initial='subscribe')

    def clean(self):
        data = super(NewsletterForm, self).clean()
        email = data.get('email')

        if not email:
            return data

        action = data.get('action')
        if (action == 'subscribe' and Subscription.objects.filter(
                email=email,
                is_active=True,
                ).exists()):
            raise forms.ValidationError(
                _('This address is already subscribed to our newsletter.'))

        elif (action == 'unsubscribe' and not Subscription.objects.filter(
                email=email,
                is_active=True,
                ).exists()):
            raise forms.ValidationError(
                _('This address is not subscribed to our newsletter.'))

        return data


def form(request):
    if request.method == 'POST':
        form = NewsletterForm(request.POST)

        if form.is_valid():
            action = form.cleaned_data['action']
            email = form.cleaned_data['email']

            if action == 'subscribe':
                send_subscription_mail(email, request)
                messages.success(request,
                    _('You should receive a confirmation email shortly.'))
            else:
                subscription = Subscription.objects.get(email=email)
                subscription.is_active = False
                subscription.save()
                send_unsubscription_mail(email, request)
                messages.success(request, _('You have been unsubscribed.'))

                unsubscribed.send(sender=Subscription,
                    request=request, subscription=subscription)

            return redirect('.')

    else:
        form = NewsletterForm()

    return render(request, 'newsletter_subscription/form.html', {
        'form': form,
        })


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        exclude = ('email', 'is_active')


def subscribe(request, code, form_class=SubscriptionForm):
    # TODO exception handling
    email = get_signer().unsign(code)
    subscription, created = Subscription.objects.get_or_create(
        email=email, defaults={'is_active': True})

    if not subscription.is_active:
        messages.success(request, _('Your subscription has been activated.'))
        subscription.is_active = True
        subscription.save()

        subscribed.send(sender=Subscription,
            request=request, subscription=subscription)

    if form_class is None:
        return redirect('newsletter_subscription_form')

    elif form_class and request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=subscription)

        if form.is_valid():
            messages.success(request,
                _('Thank you! The subscription has been updated.'))
            form.save()

            return redirect('.')

    else:
        form = form_class(instance=subscription)

    return render(request, 'newsletter_subscription/subscribe.html', {
        'subscription': subscription,
        'form': form,
        })


def resubscribe(request, code):
    # TODO exception handling
    email = get_signer().unsign(code)
    try:
        subscription = Subscription.objects.get(email=email)
        if subscription.is_active:
            messages.info(request,
                _('Your subscription is already active.'))

    except Subscription.DoesNotExist:
        # Oops?
        pass

    return redirect('newsletter_subscription_subscribe', kwargs={
        'code': code,
        })
