from django.views.generic import TemplateView

from koe.model_utils import get_user_databases, get_current_similarity, assert_permission, get_or_error
from koe.models import AudioFile, Database, DatabaseAssignment, DatabasePermission, AccessRequest
from root.models import User


def populate_context(page_name, context, request, kwargs, with_similarity=False):
    user = request.user
    databases, current_database = get_user_databases(user)
    db_assignment = assert_permission(user, current_database, DatabasePermission.VIEW)

    inaccessible_databases = Database.objects.exclude(id__in=databases)

    databases_own = DatabaseAssignment.objects \
        .filter(user=user, permission__gte=DatabasePermission.ASSIGN_USER).values_list('database', flat=True)

    pending_requests = AccessRequest.objects.filter(database__in=databases_own, resolved=False)

    context['databases'] = databases
    context['current_database'] = current_database
    context['current_database_owner_class'] = User.__name__
    context['inaccessible_databases'] = inaccessible_databases
    context['db_assignment'] = db_assignment
    context['pending_requests'] = pending_requests

    from_user = kwargs.get('from_user', user.username)
    from_user = get_or_error(User, dict(username=from_user))

    cls = kwargs.get('class', 'label')
    context['from_user'] = from_user

    context['cls'] = cls
    context['page'] = '/{}/'.format(page_name)
    context['subpage'] = '/{}/{}/'.format(page_name, cls)

    if with_similarity:
        similarities, current_similarity = get_current_similarity(user, current_database)
        context['similarities'] = similarities

        if current_similarity:
            context['current_similarity_owner_class'] = User.__name__
            context['current_similarity'] = current_similarity


class SyllablesView(TemplateView):
    """
    The view to index page
    """

    page_name = 'syllables'
    template_name = 'syllables.html'

    def get_context_data(self, **kwargs):
        context = super(SyllablesView, self).get_context_data(**kwargs)

        populate_context(SyllablesView.page_name, context, self.request, kwargs, True)

        return context


class ExemplarsView(TemplateView):
    page_name = 'exemplars'
    template_name = "exemplars.html"

    def get_context_data(self, **kwargs):
        context = super(ExemplarsView, self).get_context_data(**kwargs)

        populate_context(ExemplarsView.page_name, context, self.request, kwargs)

        return context


class SongsView(TemplateView):
    """
    The view to index page
    """

    page_name = 'songs'
    template_name = 'songs.html'

    def get_context_data(self, **kwargs):
        context = super(SongsView, self).get_context_data(**kwargs)

        populate_context(SongsView.page_name, context, self.request, kwargs)

        return context


class SegmentationView(TemplateView):
    """
    The view of song segmentation page
    """

    template_name = "segmentation.html"

    def get_context_data(self, **kwargs):
        context = super(SegmentationView, self).get_context_data(**kwargs)
        user = self.request.user

        file_id = get_or_error(kwargs, 'file_id')
        audio_file = get_or_error(AudioFile, dict(id=file_id))
        db_assignment = assert_permission(user, audio_file.database, DatabasePermission.VIEW)

        context['page'] = 'segmentation'
        context['file_id'] = file_id
        context['length'] = audio_file.length
        context['fs'] = audio_file.fs
        context['db_assignment'] = db_assignment
        return context
