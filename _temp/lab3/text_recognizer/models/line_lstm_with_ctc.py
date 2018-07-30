from functools import partial
from typing import Tuple

from boltons.cacheutils import cachedproperty
import editdistance
import numpy as np
import tensorflow as tf
import tensorflow.keras.backend as K
from tensorflow.python.client import device_lib
from tensorflow.keras.layers import Conv2D, Dense, Dropout, Flatten, Input, MaxPooling2D, Permute, Reshape, TimeDistributed, Lambda, LSTM, GRU, CuDNNLSTM, Bidirectional
from tensorflow.keras.models import Sequential
from tensorflow.keras.models import Model as KerasModel

from text_recognizer.models.dataset_sequence import DatasetSequence
from text_recognizer.models.line_model import LineModel
from text_recognizer.networks.cnn import lenet
from text_recognizer.networks.ctc import ctc_decode


class LineLstmWithCtc(LineModel):
    def __init__(self, window_width: int=14, window_stride: int=14):
        super().__init__()
        self.window_width = window_width
        self.window_stride = window_stride
        # TODO: compute this in terms of window_width, window_stride, and self.input_shape
        self.input_sequence_length = self.max_length * 2
        self.batch_format_fn = partial(format_batch, input_sequence_length=self.input_sequence_length)

    @cachedproperty
    def model(self):
        return create_sliding_window_rnn_with_ctc_model(self.input_shape, self.max_length, self.num_classes, self.window_width, self.window_stride)

    def fit(self, dataset, batch_size, epochs, callbacks):
        self.model.compile(loss=self.loss, optimizer=self.optimizer, metrics=self.metrics)

        train_sequence = DatasetSequence(dataset.x_train, dataset.y_train, batch_size, format_fn=self.batch_format_fn)
        test_sequence = DatasetSequence(dataset.x_test, dataset.y_test, batch_size, format_fn=self.batch_format_fn)

        self.model.fit_generator(
            train_sequence,
            epochs=epochs,
            callbacks=callbacks,
            validation_data=test_sequence,
            use_multiprocessing=True,
            workers=1,
            shuffle=True
        )

    def evaluate(self, x, y, batch_size: int=32) -> float:
        decoding_model = KerasModel(inputs=self.model.input, outputs=self.model.get_layer('ctc_decoded').output)
        test_sequence = DatasetSequence(x, y, batch_size, format_fn=self.batch_format_fn)
        # Your code below here (Lab 3)

        # Your code above here (Lab 3)
        char_accuracies = [
            1 - editdistance.eval(true_string, pred_string) / len(pred_string)
            for true_string, pred_string in zip(pred_strings, true_strings)
        ]
        mean_accuracy = np.mean(char_accuracies)
        return mean_accuracy

    @property
    def loss(self):
        """Dummy loss function: just pass through the loss that we computed in the network."""
        return {'ctc_loss': lambda y_true, y_pred: y_pred}

    @property
    def metrics(self):
        """We could probably pass in a custom character accuracy metric for 'ctc_decoded' output here."""
        return None

    def predict_on_image(self, image: np.ndarray) -> Tuple[str, float]:
        softmax_output_fn = K.function(
            [self.model.get_layer('image').input, K.learning_phase()],
            [self.model.get_layer('softmax_output').output]
        )
        if image.dtype == np.uint8:
            image = (image / 255).astype(np.float32)

        # Your code below here (Lab 3)

        # Your code above here (Lab 3)
        return pred, conf


def format_batch(batch_x, batch_y, input_sequence_length):
    """
    Because CTC loss needs to be computed inside of the network, we include information about outputs in the inputs.
    """
    batch_size = batch_y.shape[0]
    y_true = np.argmax(batch_y, axis=-1)
    batch_inputs = {
        'image': batch_x,
        'y_true': y_true,
        'input_length': np.ones((batch_size, 1)) * input_sequence_length,
        'label_length': np.array([np.where(batch_y[ind, :, -1] == 1)[0][0] for ind in range(batch_size)])
    }
    batch_outputs = {
        'ctc_loss': np.zeros(batch_size),  # dummy
        'ctc_decoded': y_true
    }
    return batch_inputs, batch_outputs


def create_sliding_window_rnn_with_ctc_model(input_shape, max_length, num_classes, window_width, window_stride):
    def slide_window(image, window_width=window_width, window_stride=window_stride):
        kernel = [1, 1, window_width, 1]
        strides = [1, 1, window_stride, 1]
        patches = tf.extract_image_patches(image, kernel, strides, [1, 1, 1, 1], 'SAME')
        patches = tf.transpose(patches, (0, 2, 1, 3))
        patches = tf.expand_dims(patches, -1)
        return patches

    image_height, image_width = input_shape
    image_input = Input(shape=input_shape, name='image')
    y_true = Input(shape=(max_length,), name='y_true')
    input_length = Input(shape=(1,), name='input_length')
    label_length = Input(shape=(1,), name='label_length')

    gpu_present = len(device_lib.list_local_devices()) > 1
    lstm_fn = CuDNNLSTM if gpu_present else LSTM

    # Your code below here (Lab 3)

    # Your code above here (Lab 3)

    ctc_loss_output = Lambda(
        lambda x: K.ctc_batch_cost(x[0], x[1], x[2], x[3]),
        name='ctc_loss'
    )([y_true, softmax_output, input_length, label_length])

    ctc_decoded_output = Lambda(
        lambda x: ctc_decode(x[0], x[1]),
        name='ctc_decoded'
    )([softmax_output, input_length])

    model = KerasModel(
        inputs=[image_input, y_true, input_length, label_length],
        outputs=[ctc_loss_output, ctc_decoded_output]
    )
    model.summary()
    return model