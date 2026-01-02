import os
import numpy as np
import tensorflow as tf
import librosa

#### CONFIGURACION ####
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(CURRENT_DIR, "model", "birdnet_model.tflite")
LABELS_PATH = os.path.join(CURRENT_DIR, "model", "birdnet_labels.txt")

class BirdAnalyzer:
    def __init__(self):
        # Cargamos el model TFLite
        self.interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        self.interpreter.allocate_tensors()

        # Obtenemos los inputs y outpus del modelo
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

        # IMPORTANTE AQUI CARGAMOS LA LISTA DE NOMBRE DE PAJAROS
        self.labels = self._load_labels(LABELS_PATH)
        print("El modelo cargo de manera correcta")

    def _load_labels(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines()]
        
    def predict(self, audio_data):
        """
        Analiza un archivo de audio y deveuvle las predicciones del modelo, sabiend que birdNet trabaja
        analiza con chunks de 3 segundos a 48.000 Hz
        """
        #1. Cargamos el audio a 48.000
        sig, rate = librosa.load(audio_data, sr=48000, mono = True)

        #2. importante definit el tamaño de los chunk 
        chunk_size = 3.0
        chunk_sample = int(chunk_size * rate)

        detections = []

        #3.Recorreremos el audio en espacios de 3 seegundos
        for i in range(0, len(sig), chunk_sample):
            chunk = sig[i:i + chunk_sample]

            #si el trozo es mas pequeño qie el espacio de 3 segundo lo ignoramos
            if len(chunk) < chunk_sample:
                break #se ignora por simplicidad

            input_data = np.array([chunk],dtype=np.float32)

            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            output_data = self.interpreter.get_tensor(self.output_details[0]['index'])[0]

            top_pred = output_data.argsort()[-3:][::-1]  # top 3 predicciones

            for idx in top_pred:
                puntuacion = output_data[idx]
                if puntuacion > 0.5:  # umbral de confianza
                    detections.append({
                        "species": self.labels[idx],
                        "confidence": float(puntuacion),
                        "time_start": i/rate,
                        "time_end": (i + chunk_sample)/rate
                    })
        
        return detections