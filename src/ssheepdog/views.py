from django.contrib.auth.models import User
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext
from ssheepdog.models import Login
from django.contrib.auth.decorators import permission_required
from ssheepdog.forms import UserProfileForm, AccessFilterForm
from django.db.models import Q
from django.core.exceptions import PermissionDenied


@permission_required('ssheepdog.can_view_access_summary')
def view_access_summary(request):
    users = (User.objects
             .select_related('_profile_cache')
             .order_by('_profile_cache__nickname'))
    logins = (Login.objects
              .select_related('client', 'machine')
              .order_by('client__nickname', 'machine__nickname', 'username'))
    filter_form = AccessFilterForm(request.GET)
    u, l = filter_form.data.get('user'), filter_form.data.get('login')
    if u:
        users = users.filter(Q(username__icontains=u)
                             | Q(email__icontains=u)
                             | Q(first_name__icontains=u)
                             | Q(last_name__icontains=u)
                             | Q(_profile_cache__nickname__icontains=u)
                             )
    if l:
        logins = logins.filter(Q(username__icontains=l)
                               | Q(client__nickname__icontains=l)
                               | Q(client__description__icontains=l)
                               | Q(machine__nickname__icontains=l)
                               | Q(machine__hostname__icontains=l)
                               | Q(machine__ip__icontains=l)
                               | Q(machine__description__icontains=l))


    # To conserve DB queries, pre load all relations as a dict
    # {(3,4): True} means user w/ 3 can access login w/ id 4
    rel_list = Login.users.through.objects.values("user_id", "login_id")
    user_login_rel = dict([((x['user_id'], x['login_id']), True) for x in rel_list])

    for login in logins:
        login.entries = get_user_login_info(login, users, user_login_rel)

    return render_to_response('view_grid.html',
        {'users': users, 'logins': logins, 'filter_form': filter_form},
        context_instance=RequestContext(request))

    
def get_user_login_info(login, users, user_login_rel):
    """
    Return a dict of data for each user; it's important
    that the users remain in the same order.
    """
    login_is_active = login.is_active and login.machine.is_active

    info = []
    for user in users:
        is_allowed = (user.pk, login.pk) in user_login_rel
        is_active =  user.is_active and login_is_active

        verb = "is" if is_active else "would be"
        adjective = "permitted to access" if is_allowed else "forbidden from"
        explanations = []
        if not user.is_active:
            explanations.append("user were active")
        if not login.is_active:
            explanations.append("login were active")
        if not login.machine.is_active:
            explanations.append("machine were active")
        if_ = " if " if is_allowed else " even if "
        explanation = if_ + " and ".join(explanations) if explanations else ""

        tooltip = "%s %s %s %s@%s%s" % (user,
                                        verb, adjective,
                                        login.username,
                                        login.machine.hostname or login.machine.ip,
                                        explanation)
        info.append({'is_active': is_active,
                     'is_allowed': is_allowed,
                     'tooltip': tooltip,
                     'user': user})
    return info


@permission_required('ssheepdog.can_view_access_summary')
def user_admin_view(request,id=None):
    user = User.objects.select_related('_profile_cache').get(pk=id)
    profile = user.get_profile()

    if request.method == 'POST' and request.user.pk == user.pk:
        # Can only edit your own ssh key through this interface
        if not request.user.has_perm('ssheepdog.can_edit_own_public_key'):
            raise PermissionDenied
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('ssheepdog.views.view_access_summary')
    else:
        form = UserProfileForm(instance=profile)
    return render_to_response('user_view.html', {'user': user, 'form': form},
                              context_instance=RequestContext(request))


@permission_required('ssheepdog.can_view_access_summary')
def login_admin_view(request,id=None):
    return render_to_response('login_view.html',
            {'login': Login.objects.get(pk=id)},
            context_instance=RequestContext(request))


@permission_required('ssheepdog.can_sync')
def sync_keys(request):
    pk = request.POST.get('pk', None)
    if pk:
        try:
            login = Login.objects.get(pk=pk)
            login.sync(request.user)
        except Login.DoesNotExist:
            pass
    else:
        Login.sync_all(request.user)
    return redirect('ssheepdog.views.view_access_summary')


@permission_required('ssheepdog.can_sync')
def generate_new_application_key(request):
    from ssheepdog.utils import generate_new_application_key
    generate_new_application_key()
    return redirect('ssheepdog.views.view_access_summary')
