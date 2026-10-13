configure_file(
  input: 'betternotes.in',
  output: 'betternotes',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

betternotes_sources = files(
  'betternotes/__init__.py',
  'betternotes/application.py',
  'betternotes/main_window.py',
  'betternotes/note_window.py',
  'betternotes/note_card.py',
  'betternotes/note.py',
  'betternotes/note_store.py',
  'betternotes/rich_text_serializer.py',
  'betternotes/rich_text_toolbar.py',
  'betternotes/auto_save.py',
  'betternotes/colors.py',
  'betternotes/constants.py',
  'betternotes/shortcuts.py',
  'betternotes/preferences.py',
  'betternotes/i18n.py',
  'betternotes/plan.py',
  'betternotes/backup.py',
  'betternotes/font_settings.py',
)

install_data(
  betternotes_sources,
  install_dir: moduledir,
)
