"""Run quality logging dialog — rate runs and add notes."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QRadioButton,
    QButtonGroup,
    QTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QGroupBox,
)
from PySide6.QtCore import Qt

from src.core.run_logger import log_run, read_run_log, list_csv_files


class LogDialog(QDialog):
    """Dialog for rating a run and viewing existing log entries."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run Log")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        # -- New entry section --
        entry_group = QGroupBox("Log a Run")
        entry_layout = QVBoxLayout(entry_group)

        # CSV file selector
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("CSV File:"))
        self._file_combo = QComboBox()
        csv_files = list_csv_files()
        if csv_files:
            self._file_combo.addItems(csv_files)
        else:
            self._file_combo.addItem("(no CSV files found)")
            self._file_combo.setEnabled(False)
        file_row.addWidget(self._file_combo, stretch=1)
        entry_layout.addLayout(file_row)

        # Rating radio buttons
        rating_row = QHBoxLayout()
        rating_row.addWidget(QLabel("Rating:"))
        self._rating_group = QButtonGroup(self)
        for value in ["good", "neutral", "bad"]:
            rb = QRadioButton(value.capitalize())
            self._rating_group.addButton(rb)
            rating_row.addWidget(rb)
            if value == "neutral":
                rb.setChecked(True)
        entry_layout.addLayout(rating_row)

        # Notes
        entry_layout.addWidget(QLabel("Notes:"))
        self._notes = QTextEdit()
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes about this run...")
        entry_layout.addWidget(self._notes)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(bool(csv_files))
        self._save_btn.clicked.connect(self._save)
        entry_layout.addWidget(self._save_btn)

        layout.addWidget(entry_group)

        # -- Existing entries table --
        layout.addWidget(QLabel("Previous Entries:"))
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Timestamp", "CSV File", "Rating", "Notes"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, stretch=1)

        self._load_table()

    def _save(self) -> None:
        filename = self._file_combo.currentText()
        checked = self._rating_group.checkedButton()
        rating = checked.text().lower() if checked else "neutral"
        notes = self._notes.toPlainText().strip()

        log_run(filename, rating, notes)

        QMessageBox.information(self, "Saved", f"Logged: {filename} = {rating}")
        self._notes.clear()
        self._load_table()

    def _load_table(self) -> None:
        df = read_run_log()
        self._table.setRowCount(len(df))
        for row_idx, (_, row) in enumerate(df.iterrows()):
            for col_idx, col in enumerate(df.columns):
                item = QTableWidgetItem(str(row[col]))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row_idx, col_idx, item)
