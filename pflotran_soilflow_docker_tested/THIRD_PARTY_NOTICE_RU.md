# Уведомление о сторонних компонентах

Этот пакет содержит только обвязку, Dockerfile, инструкции и демонстрационные входные данные. Во время `docker build` образ скачивает и собирает стороннее ПО:

```text
PFLOTRAN       https://bitbucket.org/pflotran/pflotran
PETSc          https://gitlab.com/petsc/petsc
Python packages openpyxl, numpy, pandas, h5py, matplotlib, PyYAML
Ubuntu packages from apt repositories
```

Перед коммерческим распространением контейнера нужно отдельно проверить лицензионные условия всех сторонних компонентов и способ распространения итогового Docker image. На момент подготовки пакета PFLOTRAN заявляет LGPL-лицензию, PETSc — BSD-подобную 2-clause лицензию. Этот файл не является юридическим заключением.
