How to create new Artifact Type
===============================

Basics
------

Each artifact type must realize **Glare Artifact Type Interface** (GATI)
and be inherited from ``glare.objects.base.BaseArtifact`` class.
GATI obliges to specify only one class method – ``get_type_name``
that returns a string with unique artifact type name. Other methods
and fields are optional.

.. note::

  Conventionally it is recommended to give names in the plural, in
  lowercase, with words separated by underscores.

Example of code for minimal artifact type:

  .. code-block:: python

    from glare.objects import base

    class HelloWorld(base.BaseArtifact):
        @classmethod
        def get_type_name(cls):
            return "hello_worlds"

Custom artifact fields
----------------------

Users can add type specific fields to their artifact type to extend
its logic and functionality. Follow the requirements of
oslo.versionedobjects library all new fields must be placed in class
dictionary attribute called ``fields``:

  .. code-block:: python

    from glare.objects import base

    class HelloWorld(base.BaseArtifact):
        ...
        fields = {...}

There is a large number of possible field options. Let’s look at the
most popular ones.

Fields of primitive types
^^^^^^^^^^^^^^^^^^^^^^^^^

Users are allowed to create additional fields of 5 primitive types:
  * IntegerField
  * FloatField
  * FlexibleBooleanField
  * StringField
  * Link

First four are taken from oslo.versionedobjects directly, Link is a
glare-specific field which stores links in specific format to other
artifacts in the system.

.. note::

  It’s recommended to use FlexibleBoolean field instead of just
  Boolean, because it has more sophisticated coercing. For instance,
  it accepts string parameters like “true”, “yes”, “1” and so on,
  and successfully coerces it to boolean value True.

Users can create their own fields with method ``init`` from Attribute class.
This method’s first parameter must be an appropriate field class, other
parameters are optional and will be discussed later. In next example we
will create 5 new custom fields, one for each primitive type:

  .. code-block:: python

    from oslo_versionedobjects import fields

    from glare.objects import base
    from glare.objects.meta import wrappers
    from glare.objects.meta import fields as glare_fields

    Field = wrappers.Field.init

    class HelloWorld(base.BaseArtifact):
        @classmethod
        def get_type_name(cls):
            return "hello_worlds"

        fields = {
            'my_int': Field(fields.IntegerField),
            'my_float': Field(fields.FloatField),
            'my_bool': Field(fields.FlexibleBooleanField),
            'my_string': Field(fields.StringField),
            'my_link': Field(glare_fields.Link)
        }

Compound types
^^^^^^^^^^^^^^

There are two collections, that may contain fields of primitive types:
*List* and *Dict*. Fields of compound types are created with method ``init``
of classes ListAttribute and DictAttribute respectively.
Unlike Attribute class’ ``init``, this method takes field type class as
a first parameter, but not just field class. So, *IntegerField* must be changed
to *Integer*, *FloatField* to *Float*, and so on. Finally for collection of
links user should use *LinkType*. Let’s add several new compound fields to
*HelloWorld* class.

  .. code-block:: python

    from oslo_versionedobjects import fields

    from glare.objects import base
    from glare.objects.meta import wrappers
    from glare.objects.meta import fields as glare_fields

    Field = wrappers.Field.init
    Dict = wrappers.DictField.init
    List = wrappers.ListField.init

    class HelloWorld(base.BaseArtifact):
        @classmethod
        def get_type_name(cls):
            return "hello_worlds"

        fields = {
            ...
            'my_list_of_str': List(fields.String),
            'my_dict_of_int': Dict(fields.Integer),
            'my_list_of_float': List(fields.Float),
            'my_dict_of_bools': Dict(fields.FlexibleBoolean),
            'my_list_of_links': List(glare_fields.LinkType)
        }

Other parameters, like collection max size, possible item values,
and so on, also can be specified with additional parameters to ``init``
method. They will be discussed later.

Blob and Folder types
^^^^^^^^^^^^^^^^^^^^^

The most interesting fields in glare framework are *Blob* and
*Folder* (or *BlobDict*). These fields allow users to work binary data,
which is stored in a standalone cloud storage, like Swift or Ceph.
The difference between Blob and Folder is that Blob sets unique endpoint
and may contain only one binary object, on the other hand Folder may
contain lots of binaries with names specified by user.

Example of Blob and Folder fields:

  .. code-block:: python

    from oslo_versionedobjects import fields

    from glare.objects import base
    from glare.objects.meta import wrappers
    from glare.objects.meta import fields as glare_fields

    Field = wrappers.Field.init
    Dict = wrappers.DictField.init
    List = wrappers.ListField.init
    Blob = wrappers.BlobField.init
    Folder = wrappers.FolderField.init

    class HelloWorld(base.BaseArtifact):
        @classmethod
        def get_type_name(cls):
            return "hello_worlds"

        fields = {
            ...
            'my_blob': Blob(),
            'my_folder': Folder(),
        }
