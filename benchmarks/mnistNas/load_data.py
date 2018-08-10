import os
from tensorflow.examples.tutorials.mnist import input_data
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

def load_data(dest=None):
    """Loads the MNIST dataset.
    Returns Tuple of Numpy arrays: `(train_X, train_y), (valid_X, valid_y)`.
    """
    #dest = "/projects/datascience/regele/deephyper/benchmarks/mnistNas/DATA"
    #dest = '/Users/dipendra/Projects/deephyper/benchmarks/mnistNas/DATA'
    dest = HERE+'/DATA'

    mnist = input_data.read_data_sets(dest, one_hot=False)

    train_X = mnist.train.images
    shp_X = list(np.shape(train_X))[:1] + [28, 28, 1]
    train_X = np.reshape(train_X, shp_X)

    # train_y = np.argmax(mnist.train.labels, axis=1)
    train_y = mnist.train.labels

    valid_X = mnist.validation.images
    shp_X = list(np.shape(valid_X))[:1] + [28, 28, 1]
    valid_X = np.reshape(valid_X, shp_X)

    # valid_y = np.argmax(mnist.validation.labels, axis=1)
    valid_y = mnist.validation.labels
    
    print(train_X[0])
    return (train_X, train_y), (valid_X, valid_y)

if __name__ == '__main__':
    load_data('mnist_data')
