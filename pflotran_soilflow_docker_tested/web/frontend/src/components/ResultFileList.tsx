import { useState } from "react";
import { downloadRunFile } from "../api/client";
import { ErrorNotice } from "./ErrorNotice";

interface ResultFileListProps {
  runName: string;
  files: string[];
}

export function ResultFileList({ runName, files }: ResultFileListProps) {
  const [error, setError] = useState("");

  async function downloadFile(file: string) {
    try {
      await downloadRunFile(runName, file);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось скачать файл");
    }
  }

  if (!files.length) {
    return <p className="muted">Файлы не найдены.</p>;
  }
  return (
    <>
      <ErrorNotice message={error} />
      <ul className="file-list">
        {files.map((file) => (
          <li key={file}>
            <button className="file-button" type="button" onClick={() => downloadFile(file)}>
              {file}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
