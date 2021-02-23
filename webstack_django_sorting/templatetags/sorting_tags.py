from operator import attrgetter

from django import template
from django.http import Http404
from django.utils.translation import ugettext_lazy as _

from ..settings import INVALID_FIELD_RAISES_404, SORT_DIRECTIONS
from ..utils import get_sort_field, render_sort_link


register = template.Library()


def anchor(parser, token):
    """
    Parses a tag that's supposed to be in this format '{% anchor field title %}'
    Title may be a "string", _("trans string"), or variable
    """
    bits = [b for b in token.split_contents()]
    if len(bits) < 2:
        raise template.TemplateSyntaxError("anchor tag takes at least 1 argument.")

    title_is_var = False
    title_is_translatable = False
    try:
        title = bits[2]
        if title[0] in ('"', "'"):
            if title[0] == title[-1]:
                title = title[1:-1]
            else:
                raise template.TemplateSyntaxError(
                    'anchor tag title must be a "string", _("trans string"), or variable'
                )
        elif title.startswith('_("') or title.startswith("_('"):
            title_is_translatable = True
        else:
            title_is_var = True
    except IndexError:
        title = bits[1].capitalize()

    return SortAnchorNode(
        bits[1].strip(), title.strip(), title_is_var, title_is_translatable
    )


class SortAnchorNode(template.Node):
    """
    Renders an <a> HTML tag with a link which href attribute
    includes the field on which we sort and the direction.
    and adds an up or down arrow if the field is the one
    currently being sorted on.

    Eg.
        {% anchor name Name %} generates
        <a href="/the/current/path/?sort=name&dir=asc" title="Name">Name</a>

    """

    def __init__(self, field, title, title_is_var, title_is_translatable):
        self.field = field
        self.title = title
        self.title_is_var = title_is_var
        self.title_is_translatable = title_is_translatable

    def render(self, context):
        if self.title_is_var:
            display_title = context[self.title]
        elif self.title_is_translatable:
            display_title = _(self.title[3:-2])
        else:
            display_title = self.title

        return render_sort_link(context["request"], self.field, display_title)


def autosort(parser, token):
    bits = [b.strip("\"'") for b in token.split_contents()]
    help_msg = (
        "autosort tag synopsis: {%% autosort queryset [as " "context_variable] %%}"
    )
    context_var = None

    # Check if has not required "as new_context_var" part
    if len(bits) == 4 and bits[2] == "as":
        context_var = bits[3]
        del bits[2:]

    if len(bits) != 2:
        raise template.TemplateSyntaxError(help_msg)

    return SortedDataNode(bits[1], context_var=context_var)


class SortedDataNode(template.Node):
    """
    Automatically sort a queryset with {% autosort queryset %}
    """

    def __init__(self, queryset_var, context_var=None):
        self.queryset_var = template.Variable(queryset_var)
        self.context_var = context_var

    def need_python_sorting(self, queryset, ordering):
        if ordering.find("__") >= 0:
            # Python can't sort ordering with '__'
            return False

        # Python sorting if not a field
        field = ordering[1:] if ordering[0] == "-" else ordering
        field_names = [f.name for f in queryset.model._meta.get_fields()]
        return field not in field_names

    def sort_queryset(self, queryset, ordering):
        if not ordering:
            return queryset

        if queryset.exists():
            if self.need_python_sorting(queryset, ordering):
                # Fallback on pure Python sorting (much slower on large data)

                # The field name can be prefixed by the minus sign and we need to
                # extract this information if we want to sort on simple object
                # attributes (non-model fields)
                if ordering[0] == "-":
                    if len(ordering) == 1:
                        # Prefix without field name
                        raise template.TemplateSyntaxError

                    reverse = True
                    name = ordering[1:]
                else:
                    reverse = False
                    name = ordering
                if hasattr(queryset[0], name):
                    return sorted(queryset, key=attrgetter(name), reverse=reverse)
                else:
                    raise AttributeError()
            else:
                return queryset.order_by(ordering)

        return queryset

    def render(self, context):
        if self.context_var is not None:
            key = self.context_var
        else:
            key = self.queryset_var.var

        queryset = self.queryset_var.resolve(context)
        ordering = get_sort_field(context["request"])

        try:
            context[key] = self.sort_queryset(queryset, ordering)
        except (template.TemplateSyntaxError, AttributeError):
            if INVALID_FIELD_RAISES_404:
                raise Http404(
                    "Invalid field sorting. If INVALID_FIELD_RAISES_404 were set to "
                    "False, the error would have been ignored."
                )
            context[key] = queryset

        return ""


anchor = register.tag(anchor)
autosort = register.tag(autosort)
